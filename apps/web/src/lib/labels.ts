/**
 * Centralized Russian-first label strings.
 *
 * 2026-04-18: product has a middle-aged Russian-speaking audience. Scattered
 * English "SELECT MODE", "SEND", "THINKING", "OK", "BLITZ" etc. confuses them.
 * One module owns all UI strings so translation / rewording is trivial later.
 *
 * Rule of thumb:
 *   - Headers, labels, CTA → Russian only
 *   - Short arcade accents ("▶", "✓", "✖", "●") → symbols are fine
 *   - Developer-facing (log prefixes, DB column names) → English stays
 *
 * Usage:
 *   import { L } from "@/lib/labels";
 *   <button>{L.quiz.start}</button>
 */

export const L = {
  common: {
    ok: "Понятно",
    cancel: "Отмена",
    retry: "Повторить",
    close: "Закрыть",
    back: "Назад",
    next: "Далее",
    send: "Отправить",
    save: "Сохранить",
    delete: "Удалить",
    loading: "Загрузка…",
    error: "Ошибка",
    success: "Готово",
    yes: "Да",
    no: "Нет",
    done: "Готово",
  },

  nav: {
    home: "Главная",
    training: "Тренировки",
    history: "История",
    leaderboard: "Лидерборд",
    pvp: "Арена",
    clients: "Клиенты",
    dashboard: "Панель РОП",
    stories: "AI-Портфель",
    profile: "Профиль",
    settings: "Настройки",
  },

  pvp: {
    mode_select: "Выберите режим",
    pvp_arena: "Арена PvP",
    pvp_modes: "Режимы PvP",
    pve_modes: "Режимы PvE",
    classic_duel: "Классическая дуэль",
    rapid_fire: "Скоростной бой",
    gauntlet: "Испытание",
    team_2v2: "Команда 2×2",
    standard_bot: "Стандартный бот",
    ladder: "Лестница ботов",
    boss_rush: "Штурм боссов",
    mirror_match: "Зеркальный матч",
    start_battle: "В бой",
    find_opponent: "Найти соперника",
    connecting: "Подключение к арене",
    duel_cancelled: "Дуэль отменена",
    duel_unavailable: "Дуэль недоступна",
    no_connection: "Нет связи с ареной",
    return_to_arena: "Вернуться на арену",
    calibrating: "Калибровка рейтинга",
    searching_opponent: "Ищем соперника…",
    fallback_to_pve: "Готовим бой с AI",
  },

  quiz: {
    tab_knowledge: "Знания 127-ФЗ",
    mode_free: "Свободный диалог",
    mode_blitz: "Блиц",
    mode_themed: "По теме",
    select_category: "Выберите тему",
    select_examiner: "Ведущий",
    examiner_professor: "Профессор Кодексов",
    examiner_detective: "Арбитражный Следопыт",
    examiner_blitz_auto: "Блиц-Мастер (автовыбор)",
    start: "Начать тест",
    hint: "Подсказка",
    skip: "Пропустить",
    answer_placeholder: "Введите ответ…",
    user_prefix: "Вы",
    thinking: "Обрабатываю ответ",
    thinking_messages: [
      "Ищу в кодексе…",
      "Анализирую ответ…",
      "Сверяю с 127-ФЗ…",
      "Подбираю вопрос…",
      "Проверяю практику…",
      "Загружаю…",
    ],
    correct: "Верно!",
    correct_bonus: "Верно! +XP",
    incorrect: "Неверно",
    hint_label: "Подсказка",
    follow_up: "Уточняющий вопрос (необязательно)",
    speed_bonus: "Бонус за скорость",
  },

  training: {
    title: "Тренировки",
    tab_scenarios: "Сценарии",
    tab_assigned: "Назначенные",
    tab_builder: "Конструктор",
    tab_saved: "Мои клиенты",
    start_session: "Начать тренировку",
    archetypes_catalog: "Каталог архетипов",
    recommended: "Рекомендуемые",
  },

  stories: {
    title: "AI-Портфель",
    subtitle: "Ваши долгие истории с AI-клиентами",
    back_to_portfolio: "К портфелю",
    stat_active: "Активных",
    stat_total: "Историй",
    stat_continuity: "Продолжения",
    open_arc: "Открыть арку",
  },

  history: {
    title: "История",
    subtitle: "Все прошедшие тренировки",
    sessions: "Сессии",
    scores: "Оценки",
    completed: "Завершена",
    aborted: "Прервана",
    review: "Разбор",
  },

  leaderboard: {
    title: "Лидерборд",
    subtitle: "Рейтинг охотников",
    tab_hunter: "Охотник",
    tab_week: "Неделя",
    tab_month: "Месяц",
    tab_arena: "Арена",
    tab_knowledge: "Знания",
    level_short: "Ур.",
  },

  auth: {
    login: "Войти",
    register: "Регистрация",
    logout: "Выход",
    forgot_password: "Забыли пароль?",
    reset_password: "Сброс пароля",
    email: "Почта",
    password: "Пароль",
    full_name: "Полное имя",
  },

  toast: {
    session_error: "Не удалось создать сессию. Попробуйте ещё раз.",
    network_error: "Проблема с подключением. Проверьте интернет.",
    generic_error: "Что-то пошло не так. Попробуйте позже.",
    saved: "Сохранено",
  },
} as const;

export type Labels = typeof L;
