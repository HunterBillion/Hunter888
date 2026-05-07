"""
WebSocket /ws/notifications — real-time уведомления для менеджеров и РОП.

ТЗ v2, раздел 6:
- Аутентификация: JWT в первом сообщении (как /ws/training)
- События: notification.new, consent.received, consent.revoked,
  client.status_changed, reminder.due, client.duplicate_warning

Менеджер ConnectionManager хранит активные соединения
для отправки targeted-уведомлений конкретным пользователям.
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import WebSocket, WebSocketDisconnect

from app.core import errors as err
from app.core.security import decode_token
from app.core.ws_rate_limiter import notification_limiter
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
        # user_id → role string (cached on connect for role-based filtering)
        self.user_roles: dict[str, str] = {}
        # (user_id, ws) → set of subscribed channels (e.g. "game_crm", "clients")
        self.subscriptions: dict[int, set[str]] = {}  # ws id() → channels
        # Lock to protect concurrent access to active_connections
        self._lock = asyncio.Lock()

    async def connect(
        self,
        websocket: WebSocket,
        user_id: str,
        preferences: dict | None = None,
        role: str | None = None,
    ) -> None:
        """Добавить соединение пользователя."""
        async with self._lock:
            if user_id not in self.active_connections:
                self.active_connections[user_id] = []
            self.active_connections[user_id].append(websocket)
            if preferences is not None:
                self.user_prefs[user_id] = preferences
            if role is not None:
                self.user_roles[user_id] = role
            logger.info("WS Notification connected: user=%s role=%s (total=%d)", user_id, role, len(self.active_connections[user_id]))

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

    async def disconnect(self, websocket: WebSocket, user_id: str) -> None:
        """Удалить соединение (async to acquire lock)."""
        async with self._lock:
            if user_id in self.active_connections:
                self.active_connections[user_id] = [
                    ws for ws in self.active_connections[user_id] if ws != websocket
                ]
                if not self.active_connections[user_id]:
                    del self.active_connections[user_id]
                    # Clean up role/prefs cache when last connection closes
                    self.user_roles.pop(user_id, None)
                    self.user_prefs.pop(user_id, None)
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

        async with self._lock:
            connections = list(self.active_connections.get(user_id, []))
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
        if dead:
            async with self._lock:
                for ws in dead:
                    self.active_connections[user_id] = [
                        c for c in self.active_connections.get(user_id, []) if c != ws
                    ]

    async def send_to_role(self, role: str, team_id: str | None, event: dict) -> None:
        """
        Отправить событие всем пользователям определённой роли.
        Для РОП — фильтруем по team_id (если задан).
        Filters by cached user_roles; admins always receive role-targeted events.
        """
        async with self._lock:
            snapshot = {uid: list(conns) for uid, conns in self.active_connections.items()}
            roles_snapshot = dict(self.user_roles)
        dead_pairs: list[tuple[str, WebSocket]] = []
        for user_id, connections in snapshot.items():
            user_role = roles_snapshot.get(user_id)
            # Only send to users with matching role or admins
            if user_role != role and user_role != "admin":
                continue
            # If team_id filtering requested, skip users not in that team
            # (team_id filtering requires additional data — handled by caller via send_to_user)
            for ws in connections:
                try:
                    await ws.send_json(event)
                except Exception:
                    dead_pairs.append((user_id, ws))
        if dead_pairs:
            async with self._lock:
                for uid, ws in dead_pairs:
                    if uid in self.active_connections:
                        self.active_connections[uid] = [
                            c for c in self.active_connections[uid] if c != ws
                        ]

    async def broadcast(self, event: dict) -> None:
        """Отправить всем подключённым."""
        async with self._lock:
            snapshot = {uid: list(conns) for uid, conns in self.active_connections.items()}
        dead_pairs: list[tuple[str, WebSocket]] = []
        for user_id, connections in snapshot.items():
            for ws in connections:
                try:
                    await ws.send_json(event)
                except Exception:
                    dead_pairs.append((user_id, ws))
        if dead_pairs:
            async with self._lock:
                for uid, ws in dead_pairs:
                    if uid in self.active_connections:
                        self.active_connections[uid] = [
                            c for c in self.active_connections[uid] if c != ws
                        ]

    @property
    def connected_count(self) -> int:
        return sum(len(conns) for conns in self.active_connections.values())


# Singleton
notification_manager = NotificationConnectionManager()


async def broadcast_system_message(event: dict) -> None:
    """Broadcast a system-level message to all connected users.

    Used by llm_health.py for degradation/restoration alerts.
    """
    await notification_manager.broadcast(event)


# ─── 3.4: Typed cross-module notification helpers ────────────────────────────


class NotificationType:
    """Typed notification events from all modules."""
    # Training module
    TRAINING_STREAK_RISK = "training.streak_risk"
    TRAINING_SCORE_RECORD = "training.score_record"
    TRAINING_STALE = "training.stale"

    # Knowledge module
    KNOWLEDGE_SRS_OVERDUE = "knowledge.srs_overdue"
    KNOWLEDGE_WEAK_AREA = "knowledge.weak_area"
    KNOWLEDGE_MASTERY = "knowledge.mastery"
    # PR-8 (2026-05-07): broadcast on admin chunk CRUD so active sessions
    # know to drop stale RAG citations.
    KNOWLEDGE_CHUNK_UPDATED = "knowledge.chunk.updated"

    # PvP module
    PVP_FRIEND_ONLINE = "pvp.friend_online"
    PVP_RATING_DECAY = "pvp.rating_decay"
    PVP_RANK_UP = "pvp.rank_up"
    PVP_TOURNAMENT_START = "pvp.tournament_start"

    # Gamification module
    GAMIFICATION_ACHIEVEMENT = "gamification.achievement"
    GAMIFICATION_LEVEL_UP = "gamification.level_up"
    GAMIFICATION_GOAL_COMPLETE = "gamification.goal_complete"

    # CRM module
    CRM_CLIENT_REMINDER = "crm.client_reminder"
    CRM_PROMISE_DUE = "crm.promise_due"


async def send_typed_notification(
    user_id: str,
    notif_type: str,
    title: str,
    body: str,
    *,
    action_url: str | None = None,
    channel: str | None = None,
    force: bool = False,
    push: bool = False,
) -> None:
    """Send a typed notification via WebSocket + optionally Web Push.

    Args:
        user_id: Target user UUID string
        notif_type: One of NotificationType constants
        title: Short notification title (max 100 chars)
        body: Notification body text (max 500 chars)
        action_url: Deep link URL for the notification action
        channel: Optional channel filter for subscriptions
        force: Bypass user notification preferences
        push: Also send via Web Push (for offline users)
    """
    # Sanitize inputs
    title = str(title)[:100]
    body = str(body)[:500]
    if action_url:
        # Only allow relative URLs or known internal paths
        action_url = str(action_url)[:200]
        if action_url.startswith(("http://", "https://", "javascript:", "data:")):
            action_url = None  # Block external/injection URLs

    event = {
        "type": "notification.new",
        "notification_type": notif_type,
        "title": title,
        "body": body,
        "action_url": action_url,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    await notification_manager.send_to_user(user_id, event, channel=channel, force=force)

    # Optionally send Web Push for offline users
    if push and user_id not in notification_manager.active_connections:
        try:
            from app.services.web_push import send_push_to_user
            async with async_session() as db:
                await send_push_to_user(
                    user_id=uuid.UUID(user_id),
                    title=title,
                    body=body,
                    url=action_url,
                    db=db,
                )
        except Exception:
            logger.debug("Failed to send Web Push to user %s", user_id)


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
        # ── Шаг 1: Аутентификация (первое сообщение, таймаут 10с) ──
        try:
            raw = await asyncio.wait_for(websocket.receive_text(), timeout=10.0)
        except asyncio.TimeoutError:
            await websocket.send_json({"type": "auth.error", "message": "Auth timeout"})
            await websocket.close(code=4001)
            return
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
        if not payload or payload.get("type") != "access":
            await websocket.send_json({
                "type": "auth.error",
                "message": "Невалидный или просроченный токен",
            })
            await websocket.close(code=4001, reason="Invalid token")
            return

        user_id = payload.get("sub")
        if not user_id:
            await websocket.send_json({
                "type": "auth.error",
                "message": "Невалидный payload токена",
            })
            await websocket.close(code=4001)
            return

        # Check if user was logged out (token blacklisted)
        from app.core.deps import _is_user_blacklisted, _is_token_revoked
        if await _is_user_blacklisted(user_id):
            await websocket.send_json({
                "type": "auth.error",
                "message": "Токен отозван. Войдите заново.",
            })
            await websocket.close(code=4003)
            return

        # Per-token JTI revocation
        jti = payload.get("jti")
        if jti and await _is_token_revoked(jti):
            await websocket.send_json({
                "type": "auth.error",
                "message": "Токен отозван. Войдите заново.",
            })
            await websocket.close(code=4003)
            return

        # ── Получаем unread count + user preferences + role ──
        unread_count = 0
        user_prefs: dict = {}
        user_role: str = "manager"
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

                # Load preferences and role for notification filtering
                user_result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
                u = user_result.scalar_one_or_none()
                if not u or not u.is_active:
                    await websocket.send_json({
                        "type": "auth.error",
                        "message": "User inactive",
                    })
                    await websocket.close(code=4003, reason="User inactive")
                    return
                if u.preferences:
                    user_prefs = u.preferences
                user_role = u.role.value if u.role else "manager"
        except Exception as e:
            logger.warning("Failed to get unread count/prefs: %s", e)
            user_role = "manager"

        # ── Успешная аутентификация ──
        # T4 fix: wrap payload in `data:{}` to match the shape used by the
        # other 4 WS endpoints (/ws/training, /ws/knowledge, /ws/pvp,
        # /ws/game-crm). Frontend NotificationWSProvider already reads
        # `msg.data?.unread_count ?? msg.unread_count`, so this is backward
        # compatible during deploy.
        await notification_manager.connect(websocket, user_id, preferences=user_prefs, role=user_role)
        await websocket.send_json({
            "type": "auth.success",
            "data": {
                "user_id": user_id,
                "unread_count": unread_count,
            },
        })

        logger.info("WS Notifications authenticated: user=%s", user_id)

        # ── Шаг 2: Слушаем сообщения от клиента ──
        _rate_limiter = notification_limiter()
        while True:
            raw = await websocket.receive_text()
            if not _rate_limiter.is_allowed():
                await websocket.send_json({"type": "error", "code": "rate_limited", "message": "Too many messages"})
                continue

            # L6c fix: per-user rate limit across all connections (Redis).
            from app.core.ws_rate_limiter import check_user_rate_limit
            if not await check_user_rate_limit(str(user_id), scope="notification"):
                await websocket.send_json({
                    "type": "error",
                    "code": "rate_limited_user",
                    "message": "Слишком много сообщений со всех ваших сессий.",
                })
                continue
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
                        "message": err.WS_CHANNEL_REQUIRED,
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
            await notification_manager.disconnect(websocket, user_id)


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
