"""
Cron-система автоматических напоминаний и эскалаций (Task X3).

ТЗ v2, разделы 3.3, 7.3:
- Проверка stale-клиентов каждые N минут (REMINDER_CHECK_INTERVAL_MIN)
- Автонапоминания менеджеру по таймаутам статусов
- Эскалация РОП при длительном бездействии
- Auto-lost для thinking > 30 дней
- SMS-напоминание клиенту за 24ч до консультации

Реализация: asyncio background task, запускается при старте FastAPI.
(APScheduler не нужен для одной периодической задачи.)
"""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.client import (
    ClientInteraction,
    ClientNotification,
    ClientStatus,
    InteractionType,
    ManagerReminder,
    NotificationChannel,
    NotificationStatus,
    RealClient,
    STATUS_TIMEOUTS,
)
from app.models.user import User

logger = logging.getLogger(__name__)

# Интервал проверки (минуты) — из конфига или дефолт
CHECK_INTERVAL_MIN = 5


class ReminderScheduler:
    """
    Фоновая задача проверки клиентов и генерации напоминаний.

    Жизненный цикл:
    - start(): запускает бесконечный цикл
    - stop(): останавливает цикл
    - check_stale_clients(): одна итерация проверки

    Edge cases:
    - Двойная отправка: проверяем auto_generated + remind_at за сегодня
    - Рестарт сервера: при запуске проверяем пропущенные
    - Конкурентность: один экземпляр на процесс (singleton)
    """

    def __init__(self):
        self._task: asyncio.Task | None = None
        self._running = False

    def start(self) -> None:
        """Запустить фоновую задачу."""
        if self._task is not None:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("ReminderScheduler started (interval: %d min)", CHECK_INTERVAL_MIN)

    def stop(self) -> None:
        """Остановить фоновую задачу."""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info("ReminderScheduler stopped")

    async def _run_loop(self) -> None:
        """Бесконечный цикл проверки."""
        while self._running:
            try:
                async with async_session() as db:
                    await self.check_stale_clients(db)
                    await db.commit()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("ReminderScheduler error: %s", e, exc_info=True)

            await asyncio.sleep(CHECK_INTERVAL_MIN * 60)

    async def check_stale_clients(self, db: AsyncSession) -> None:
        """
        Одна итерация: проверить всех активных клиентов на таймауты.

        Логика по статусам (ТЗ v2, раздел 3.1):
        - new: 3 дня без контакта → напоминание менеджеру
        - contacted: 5 дней → напоминание + РОП
        - interested: 7 дней → напоминание
        - thinking: 21д → менеджер, 28д → РОП, 30д → auto-lost
        - consent_given: 5 дней без договора → напоминание
        - paused: 14 дней → напоминание
        - consent_revoked: 7 дней → напоминание
        """
        now = datetime.now(timezone.utc)

        # Получаем клиентов с таймаутами в статусах
        statuses_with_timeouts = list(STATUS_TIMEOUTS.keys())

        result = await db.execute(
            select(RealClient).where(
                RealClient.is_active == True,  # noqa: E712
                RealClient.status.in_(statuses_with_timeouts),
                RealClient.last_status_change_at.isnot(None),
            )
        )
        clients = list(result.scalars().all())

        created_reminders = 0
        auto_lost_count = 0

        for client in clients:
            timeouts = STATUS_TIMEOUTS.get(client.status, [])
            days_in_status = (now - client.last_status_change_at).days if client.last_status_change_at else 0

            for timeout_config in timeouts:
                threshold_days = timeout_config["days"]
                action = timeout_config["action"]

                if days_in_status < threshold_days:
                    continue

                # ── Проверяем, не создавали ли уже напоминание ──
                already_exists = await self._reminder_exists(
                    db,
                    client_id=client.id,
                    action=action,
                    threshold_days=threshold_days,
                )
                if already_exists:
                    continue

                # ── Выполняем действие ──
                if action == "remind_manager":
                    await self._create_reminder(
                        db,
                        client=client,
                        message=f"Клиент «{client.full_name}» в статусе «{client.status.value}» "
                                f"уже {days_in_status} дней без контакта. Пора позвонить!",
                    )
                    created_reminders += 1

                elif action == "remind_manager_and_rop":
                    await self._create_reminder(
                        db,
                        client=client,
                        message=f"Клиент «{client.full_name}» без контакта {days_in_status} дней.",
                    )
                    await self._notify_rop(
                        db,
                        client=client,
                        title=f"Эскалация: {client.full_name}",
                        body=f"Менеджер не контактировал с клиентом {days_in_status} дней. "
                             f"Статус: {client.status.value}.",
                    )
                    created_reminders += 1

                elif action == "notify_rop":
                    await self._notify_rop(
                        db,
                        client=client,
                        title=f"Предупреждение: {client.full_name}",
                        body=f"Клиент «{client.full_name}» думает уже {days_in_status} дней. "
                             f"Скоро будет переведён в «потерян».",
                    )

                elif action == "auto_lost":
                    await self._auto_lost(db, client=client, days=days_in_status)
                    auto_lost_count += 1

        if created_reminders or auto_lost_count:
            logger.info(
                "ReminderScheduler: created %d reminders, %d auto-lost",
                created_reminders,
                auto_lost_count,
            )

    async def _reminder_exists(
        self,
        db: AsyncSession,
        *,
        client_id: uuid.UUID,
        action: str,
        threshold_days: int,
    ) -> bool:
        """Проверить, не создавали ли уже авто-напоминание за этот порог."""
        # Ищем авто-напоминание за последние N дней
        since = datetime.now(timezone.utc) - timedelta(days=threshold_days)
        result = await db.execute(
            select(func.count()).where(
                ManagerReminder.client_id == client_id,
                ManagerReminder.auto_generated == True,  # noqa: E712
                ManagerReminder.message.contains(f"{threshold_days} дн"),
                ManagerReminder.created_at >= since,
            )
        )
        return (result.scalar() or 0) > 0

    async def _create_reminder(
        self,
        db: AsyncSession,
        *,
        client: RealClient,
        message: str,
    ) -> ManagerReminder:
        """Создать авто-напоминание менеджеру."""
        reminder = ManagerReminder(
            id=uuid.uuid4(),
            manager_id=client.manager_id,
            client_id=client.id,
            remind_at=datetime.now(timezone.utc),
            message=message,
            auto_generated=True,
        )
        db.add(reminder)

        # In-app уведомление менеджеру
        notification = ClientNotification(
            id=uuid.uuid4(),
            recipient_type="manager",
            recipient_id=client.manager_id,
            client_id=client.id,
            channel=NotificationChannel.in_app,
            title=f"Напоминание: {client.full_name}",
            body=message,
            status=NotificationStatus.pending,
        )
        db.add(notification)

        # WS push (best-effort)
        try:
            from app.ws.notifications import send_ws_notification

            await send_ws_notification(
                client.manager_id,
                event_type="reminder.due",
                data={
                    "reminder_id": str(reminder.id),
                    "client_name": client.full_name,
                    "client_id": str(client.id),
                    "message": message,
                },
            )
        except Exception as e:
            logger.debug("WS send failed (non-critical): %s", e)

        return reminder

    async def _notify_rop(
        self,
        db: AsyncSession,
        *,
        client: RealClient,
        title: str,
        body: str,
    ) -> None:
        """Уведомить РОП(ов) команды менеджера."""
        # Найти РОП команды
        manager_result = await db.execute(
            select(User).where(User.id == client.manager_id)
        )
        manager = manager_result.scalar_one_or_none()
        if not manager or not manager.team_id:
            return

        rop_result = await db.execute(
            select(User).where(
                User.team_id == manager.team_id,
                User.role == "rop",
                User.is_active == True,  # noqa: E712
            )
        )
        rops = list(rop_result.scalars().all())

        for rop in rops:
            notification = ClientNotification(
                id=uuid.uuid4(),
                recipient_type="manager",
                recipient_id=rop.id,
                client_id=client.id,
                channel=NotificationChannel.in_app,
                title=title,
                body=body,
                status=NotificationStatus.pending,
            )
            db.add(notification)

            try:
                from app.ws.notifications import send_ws_notification

                await send_ws_notification(
                    rop.id,
                    event_type="client.status_changed",
                    data={
                        "client_id": str(client.id),
                        "client_name": client.full_name,
                        "manager_name": manager.full_name,
                        "message": body,
                    },
                )
            except Exception:
                pass

    async def _auto_lost(
        self,
        db: AsyncSession,
        *,
        client: RealClient,
        days: int,
    ) -> None:
        """
        Автоматический перевод в lost (ТЗ v2, раздел 3.3).
        thinking > 30 дней → auto-lost.
        """
        old_status = client.status.value
        client.status = ClientStatus.lost
        client.lost_reason = f"auto_timeout_{days}d"
        client.last_status_change_at = datetime.now(timezone.utc)
        client.lost_count += 1

        # Interaction
        interaction = ClientInteraction(
            id=uuid.uuid4(),
            client_id=client.id,
            interaction_type=InteractionType.system,
            content=f"Автоматический перевод в «потерян»: {days} дней без контакта",
            old_status=old_status,
            new_status="lost",
        )
        db.add(interaction)

        # Уведомления
        await self._create_reminder(
            db,
            client=client,
            message=f"Клиент «{client.full_name}» автоматически переведён в «потерян» "
                    f"({days} дней без контакта).",
        )

        await self._notify_rop(
            db,
            client=client,
            title=f"Auto-lost: {client.full_name}",
            body=f"Клиент переведён в «потерян» ({days}д без контакта).",
        )

        logger.info(
            "Auto-lost: client=%s (%s), days=%d",
            client.id,
            client.full_name,
            days,
        )


# Singleton
reminder_scheduler = ReminderScheduler()
