"""
WebSocket /ws/notifications — real-time уведомления для менеджеров и РОП.

ТЗ v2, раздел 6:
- Аутентификация: JWT в первом сообщении (как /ws/training)
- События: notification.new, consent.received, consent.revoked,
  client.status_changed, reminder.due, client.duplicate_warning

Менеджер ConnectionManager хранит активные соединения
для отправки targeted-уведомлений конкретным пользователям.
"""

import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import WebSocket, WebSocketDisconnect

from app.core.security import decode_token
from app.database import async_session

logger = logging.getLogger(__name__)


class NotificationConnectionManager:
    """
    Управление WebSocket-соединениями для уведомлений.
    Singleton: один экземпляр на приложение.
    Respects user notification preferences (notifications, notify_push).
    """

    def __init__(self):
        # user_id → list[WebSocket]
        self.active_connections: dict[str, list[WebSocket]] = {}
        # user_id → preferences dict (cached on connect)
        self.user_prefs: dict[str, dict] = {}
        # (user_id, ws) → set of subscribed channels (e.g. "game_crm", "clients")
        self.subscriptions: dict[int, set[str]] = {}  # ws id() → channels

    async def connect(self, websocket: WebSocket, user_id: str, preferences: dict | None = None) -> None:
        """Добавить соединение пользователя."""
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)
        if preferences is not None:
            self.user_prefs[user_id] = preferences
        logger.info("WS Notification connected: user=%s (total=%d)", user_id, len(self.active_connections[user_id]))

    def subscribe(self, websocket: WebSocket, channel: str) -> None:
        """Подписать соединение на канал (e.g. 'game_crm')."""
        ws_id = id(websocket)
        if ws_id not in self.subscriptions:
            self.subscriptions[ws_id] = set()
        self.subscriptions[ws_id].add(channel)
        logger.debug("WS subscribed to channel=%s (ws=%d)", channel, ws_id)

    def unsubscribe(self, websocket: WebSocket, channel: str) -> None:
        """Отписать соединение от канала."""
        ws_id = id(websocket)
        if ws_id in self.subscriptions:
            self.subscriptions[ws_id].discard(channel)

    def disconnect(self, websocket: WebSocket, user_id: str) -> None:
        """Удалить соединение."""
        if user_id in self.active_connections:
            self.active_connections[user_id] = [
                ws for ws in self.active_connections[user_id] if ws != websocket
            ]
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
        # Clean up subscriptions
        self.subscriptions.pop(id(websocket), None)
        logger.info("WS Notification disconnected: user=%s", user_id)

    async def send_to_user(
        self,
        user_id: str,
        event: dict,
        *,
        channel: str | None = None,
        force: bool = False,
    ) -> None:
        """Отправить событие конкретному пользователю (все вкладки).

        Respects user preferences (unless force=True for critical e.g. pvp.invitation):
        - If notifications=False → skip all notifications
        - If notify_push=False → skip in-app push (WS) notifications

        Channel filtering:
        - If channel is specified, only send to connections subscribed to that channel
        - If channel is None, send to all connections (backward compatible)
        """
        if not force:
            prefs = self.user_prefs.get(user_id, {})
            if prefs.get("notifications") is False:
                return  # User disabled all notifications
            if prefs.get("notify_push") is False:
                return  # User disabled in-app notifications

        connections = self.active_connections.get(user_id, [])
        dead = []
        for ws in connections:
            # Channel filtering: if channel specified, check subscription
            if channel:
                ws_channels = self.subscriptions.get(id(ws), set())
                if channel not in ws_channels:
                    continue
            try:
                await ws.send_json(event)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.active_connections[user_id] = [
                c for c in self.active_connections.get(user_id, []) if c != ws
            ]

    async def send_to_role(self, role: str, team_id: str | None, event: dict) -> None:
        """
        Отправить событие всем пользователям определённой роли.
        Для РОП — фильтруем по team_id (если задан).
        В MVP: рассылка всем подключённым (фильтрация по роли — на стороне клиента).
        """
        for user_id, connections in self.active_connections.items():
            for ws in connections:
                try:
                    await ws.send_json(event)
                except Exception:
                    pass

    async def broadcast(self, event: dict) -> None:
        """Отправить всем подключённым."""
        for user_id, connections in self.active_connections.items():
            for ws in connections:
                try:
                    await ws.send_json(event)
                except Exception:
                    pass

    @property
    def connected_count(self) -> int:
        return sum(len(conns) for conns in self.active_connections.values())


# Singleton
notification_manager = NotificationConnectionManager()


async def notification_websocket(websocket: WebSocket) -> None:
    """
    Обработчик /ws/notifications.

    Протокол:
    1. accept()
    2. Ждём первое сообщение: {"type": "auth", "token": "<JWT>"}
    3. Валидируем JWT
    4. При успехе: {"type": "auth.success", "user_id": "...", "unread_count": N}
    5. Слушаем ping/pong, notification.read
    6. Серверные events: notification.new, consent.received, etc.
    """
    await websocket.accept()
    user_id: str | None = None

    try:
        # ── Шаг 1: Аутентификация (первое сообщение) ──
        raw = await websocket.receive_text()
        data = json.loads(raw)

        if data.get("type") != "auth":
            await websocket.send_json({
                "type": "auth.error",
                "message": "Первое сообщение должно быть auth",
            })
            await websocket.close(code=4001)
            return

        token = data.get("token") or data.get("data", {}).get("token")
        if not token:
            await websocket.send_json({
                "type": "auth.error",
                "message": "Токен не предоставлен",
            })
            await websocket.close(code=4001)
            return

        payload = decode_token(token)
        if not payload:
            await websocket.send_json({
                "type": "auth.error",
                "message": "Невалидный или просроченный токен",
            })
            await websocket.close(code=4002)
            return

        user_id = payload.get("sub")
        if not user_id:
            await websocket.send_json({
                "type": "auth.error",
                "message": "Невалидный payload токена",
            })
            await websocket.close(code=4001)
            return

        # ── Получаем unread count + user preferences ──
        unread_count = 0
        user_prefs: dict = {}
        try:
            from sqlalchemy import func, select
            from app.models.client import ClientNotification, NotificationChannel
            from app.models.user import User

            async with async_session() as db:
                result = await db.execute(
                    select(func.count()).where(
                        ClientNotification.recipient_type == "manager",
                        ClientNotification.recipient_id == uuid.UUID(user_id),
                        ClientNotification.channel == NotificationChannel.in_app,
                        ClientNotification.read_at.is_(None),
                    )
                )
                unread_count = result.scalar() or 0

                # Load preferences for notification filtering
                user_result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
                u = user_result.scalar_one_or_none()
                if u and u.preferences:
                    user_prefs = u.preferences
        except Exception as e:
            logger.warning("Failed to get unread count/prefs: %s", e)

        # ── Успешная аутентификация ──
        await notification_manager.connect(websocket, user_id, preferences=user_prefs)
        await websocket.send_json({
            "type": "auth.success",
            "user_id": user_id,
            "unread_count": unread_count,
        })

        logger.info("WS Notifications authenticated: user=%s", user_id)

        # ── Шаг 2: Слушаем сообщения от клиента ──
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            msg_type = data.get("type")

            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})

            elif msg_type == "subscribe":
                # Subscribe to a channel (e.g. "game_crm")
                ch = data.get("channel")
                if ch and isinstance(ch, str):
                    notification_manager.subscribe(websocket, ch)
                    await websocket.send_json({
                        "type": "subscribe.ok",
                        "channel": ch,
                    })
                else:
                    await websocket.send_json({
                        "type": "error",
                        "message": "channel is required for subscribe",
                    })

            elif msg_type == "unsubscribe":
                ch = data.get("channel")
                if ch and isinstance(ch, str):
                    notification_manager.unsubscribe(websocket, ch)
                    await websocket.send_json({
                        "type": "unsubscribe.ok",
                        "channel": ch,
                    })

            elif msg_type == "notification.read":
                notification_id = data.get("notification_id")
                if notification_id:
                    # Отмечаем прочитанным в БД
                    try:
                        from sqlalchemy import select
                        from app.models.client import ClientNotification, NotificationStatus

                        async with async_session() as db:
                            result = await db.execute(
                                select(ClientNotification).where(
                                    ClientNotification.id == uuid.UUID(notification_id),
                                    ClientNotification.recipient_id == uuid.UUID(user_id),
                                )
                            )
                            notif = result.scalar_one_or_none()
                            if notif:
                                notif.read_at = datetime.now(timezone.utc)
                                notif.status = NotificationStatus.read
                                await db.commit()
                    except Exception as e:
                        logger.warning("Failed to mark read: %s", e)

            else:
                await websocket.send_json({
                    "type": "error",
                    "message": f"Неизвестный тип сообщения: {msg_type}",
                })

    except WebSocketDisconnect:
        logger.info("WS Notifications disconnected: user=%s", user_id)
    except json.JSONDecodeError:
        logger.warning("WS Notifications: invalid JSON from user=%s", user_id)
        await websocket.close(code=1003)
    except Exception as e:
        logger.error("WS Notifications error: %s", e, exc_info=True)
        try:
            await websocket.close(code=1011)
        except Exception:
            pass
    finally:
        if user_id:
            notification_manager.disconnect(websocket, user_id)


# ══════════════════════════════════════════════════════════════════════════════
# HELPER: Отправка уведомлений из сервисов
# ══════════════════════════════════════════════════════════════════════════════


async def send_ws_notification(
    user_id: str | uuid.UUID,
    *,
    event_type: str,
    data: dict,
) -> None:
    """
    Отправить WS-событие пользователю.
    Вызывается из ClientService / API хендлеров.

    Типы событий:
        - notification.new: {id, title, body, type, client_id}
        - consent.received: {client_id, consent_type}
        - consent.revoked: {client_id, consent_type, reason}
        - client.status_changed: {client_id, old, new, manager}
        - reminder.due: {reminder_id, client_name, message}
        - client.duplicate_warning: {client_id, duplicate_id, phone}
    """
    event = {
        "type": event_type,
        "data": data,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    await notification_manager.send_to_user(str(user_id), event)


async def send_ws_game_crm(
    user_id: str | uuid.UUID,
    *,
    event_type: str,
    data: dict,
) -> None:
    """
    Отправить событие Game CRM через subchannel 'game_crm'.
    Только клиенты, подписанные на канал game_crm, получат событие.

    Типы событий:
        - game_crm.timeline_update: {story_id, event}
        - game_crm.status_changed: {story_id, old_status, new_status}
        - game_crm.callback_scheduled: {story_id, scheduled_for}
        - game_crm.message_sent: {story_id, event_id, content}
    """
    event = {
        "type": event_type,
        "channel": "game_crm",
        "data": data,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    await notification_manager.send_to_user(str(user_id), event, channel="game_crm")


async def send_ws_to_rop_team(
    team_id: str | None,
    *,
    event_type: str,
    data: dict,
) -> None:
    """Отправить WS-событие всем РОП команды."""
    event = {
        "type": event_type,
        "data": data,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    await notification_manager.send_to_role("rop", team_id, event)
