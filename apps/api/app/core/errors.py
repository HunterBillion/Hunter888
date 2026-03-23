"""Centralized user-facing error messages (Russian).

All HTTPException detail strings and WebSocket error messages should reference
constants from this module. This ensures:
 1. Consistent language (Russian UI = Russian errors)
 2. Single place to update/localize messages
 3. Easy auditing for user-facing strings
"""

# ── Auth & Token ─────────────────────────────────────────────────────────────

NOT_AUTHENTICATED = "Необходима авторизация"
INVALID_OR_EXPIRED_TOKEN = "Недействительный или просроченный токен"
INVALID_TOKEN = "Недействительный токен"
TOKEN_REVOKED = "Токен отозван"
TOKEN_REVOKED_RELOGIN = "Токен отозван. Пожалуйста, войдите заново."
INVALID_CREDENTIALS = "Неверный email или пароль"
ACCOUNT_DISABLED = "Аккаунт отключён"
INVALID_REFRESH_TOKEN = "Недействительный refresh-токен"
EMAIL_ALREADY_REGISTERED = "Этот email уже зарегистрирован"
CURRENT_PASSWORD_INCORRECT = "Текущий пароль неверен"

# ── Permissions ──────────────────────────────────────────────────────────────

INSUFFICIENT_PERMISSIONS = "Недостаточно прав"
OWN_STATS_ONLY = "Вы можете просматривать только свою статистику"
OWN_ANALYTICS_ONLY = "Вы можете просматривать только свою аналитику"

# ── Resources ────────────────────────────────────────────────────────────────

USER_NOT_FOUND = "Пользователь не найден"
SESSION_NOT_FOUND = "Сессия не найдена"
ACTIVE_SESSION_NOT_FOUND = "Активная сессия не найдена"
SCENARIO_NOT_FOUND = "Сценарий не найден"
TEAM_NOT_FOUND = "Команда не найдена"
NO_TEAM_ASSIGNED = "Команда не назначена"
STORY_NOT_FOUND = "История не найдена"
STORY_NOT_FOUND_OR_ACCESS_DENIED = "История не найдена или нет доступа"
RATING_NOT_FOUND = "Рейтинг не найден"
FLAG_NOT_FOUND = "Флаг не найден"
EMOTION_STATE_NOT_FOUND = "Эмоциональное состояние не найдено"
NOTIFICATION_NOT_FOUND = "Уведомление не найдено"
REMINDER_NOT_FOUND = "Напоминание не найдено"
MANAGER_NOT_FOUND = "Менеджер не найден"

# ── Training / Scenarios ─────────────────────────────────────────────────────

NO_ACTIVE_SCENARIOS = "Нет активных сценариев. Сначала запустите seed_db."
TARGET_USER_NOT_FOUND = "Целевой пользователь не найден"
TRAINING_ASSIGNED = "Тренировка успешно назначена"
DEADLINE_FORMAT_ERROR = "Дедлайн должен быть в формате ISO 8601 (например, 2026-03-25T14:00:00)"
NO_SCENARIO_TEMPLATES = "Не найдено активных шаблонов сценариев в базе данных"

# ── Tournament ───────────────────────────────────────────────────────────────

NO_ACTIVE_TOURNAMENT = "Нет активного турнира"
TOURNAMENT_MAX_ATTEMPTS = "Достигнуто максимальное количество попыток или турнир завершён"
TOURNAMENT_ALREADY_EXISTS = "Турнир на эту неделю уже существует или нет доступных сценариев"

# ── PvP / Duel ───────────────────────────────────────────────────────────────

DUEL_NOT_FOUND = "Дуэль не найдена"
NOT_A_PARTICIPANT = "Вы не являетесь участником"

# ── OAuth ────────────────────────────────────────────────────────────────────

MISSING_OAUTH_STATE = "Отсутствует параметр состояния OAuth"
INVALID_OAUTH_STATE = "Недействительное или просроченное состояние OAuth (возможная CSRF-атака)"

# ── Services ─────────────────────────────────────────────────────────────────

SERVICE_TEMPORARILY_UNAVAILABLE = "Сервис временно недоступен"

# ── Consent ──────────────────────────────────────────────────────────────────

CONSENT_ALREADY_ACCEPTED = "Это согласие уже было принято"
REQUIRED_CONSENT_NOT_ACCEPTED = "Необходимое согласие не принято"

# ── Clients ──────────────────────────────────────────────────────────────────

MISSING_SUBSCRIPTION_DATA = "Отсутствуют данные подписки"
MISSING_ENDPOINT = "Отсутствует endpoint"

# ── WebSocket ────────────────────────────────────────────────────────────────

WS_INVALID_JSON = "Некорректный JSON"
WS_FIRST_MESSAGE_AUTH = "Первое сообщение должно быть авторизацией"
WS_TOKEN_REQUIRED = "Необходим токен"
WS_INVALID_OR_EXPIRED_TOKEN = "Недействительный или просроченный токен"
WS_INVALID_TOKEN_PAYLOAD = "Некорректные данные токена"
WS_INVALID_USER_ID = "Некорректный ID пользователя в токене"
WS_USER_NOT_FOUND = "Пользователь не найден или неактивен"
WS_TOKEN_REVOKED = "Токен отозван"
WS_SESSION_ENDED = "Сессия успешно завершена"
WS_AUTH_TIMEOUT = "Таймаут авторизации"
WS_AUTHENTICATED = "Авторизация успешна. Отправьте session.start для начала."
WS_INACTIVITY_TIMEOUT = "Соединение закрыто из-за неактивности"
WS_CHANNEL_REQUIRED = "Поле channel обязательно для подписки"

# ── Calibration ──────────────────────────────────────────────────────────────

NO_CALIBRATION_DATA = "Данные калибровки не загружены."
