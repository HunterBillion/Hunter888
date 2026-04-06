/**
 * Expanded daily challenge pool (25 challenges).
 *
 * Each user sees a different challenge each day, seeded by userId + dayOfYear.
 * Cycle: ~25 days before repetition for a single user.
 */

export interface DailyChallenge {
  title: string;
  desc: string;
  type: "cold_call" | "warm_call" | "retention" | "any";
  minScore: number;
  /** Potential future XP bonus for completing the challenge */
  rewardXp: number;
}

const CHALLENGES: DailyChallenge[] = [
  // ── Переговорные навыки ───────────────────────────────────────
  { title: "Покорить скептика", desc: "Пройди сценарий с Алексеем Михайловым и набери 70+ баллов", type: "cold_call", minScore: 70, rewardXp: 50 },
  { title: "Мастер эмпатии", desc: "Доведи тревожного клиента до состояния OPEN без единого давления", type: "cold_call", minScore: 60, rewardXp: 50 },
  { title: "Укротитель агрессии", desc: "Пройди сценарий с агрессивным директором и доведи до сделки", type: "cold_call", minScore: 65, rewardXp: 60 },
  { title: "Идеальный скрипт", desc: "Набери 90%+ по показателю «Следование скрипту»", type: "cold_call", minScore: 90, rewardXp: 80 },
  { title: "Холодный мастер", desc: "Пройди 2 сценария холодного звонка подряд с 70+ баллов", type: "cold_call", minScore: 70, rewardXp: 70 },

  // ── Объём и дисциплина ────────────────────────────────────────
  { title: "3 сессии за день", desc: "Пройди 3 тренировочных сессии за сегодня", type: "any", minScore: 0, rewardXp: 40 },
  { title: "Утренняя разминка", desc: "Пройди тренировку до 10:00 утра", type: "any", minScore: 0, rewardXp: 30 },
  { title: "Марафонец", desc: "Набери суммарно 200+ баллов за день", type: "any", minScore: 0, rewardXp: 60 },
  { title: "Без поражений", desc: "Заверши 2 сессии подряд с оценкой выше 75", type: "any", minScore: 75, rewardXp: 55 },
  { title: "Ежедневная привычка", desc: "Продолжи свой streak — пройди хотя бы одну тренировку", type: "any", minScore: 0, rewardXp: 20 },

  // ── Работа с возражениями ─────────────────────────────────────
  { title: "Возражение «дорого»", desc: "Отработай возражение о цене и доведи до позитивного исхода", type: "cold_call", minScore: 65, rewardXp: 50 },
  { title: "«Мне надо подумать»", desc: "Преодолей отсрочку принятия решения", type: "cold_call", minScore: 60, rewardXp: 50 },
  { title: "Работа с отказом", desc: "Клиент начал с категоричного «нет» — измени его мнение", type: "cold_call", minScore: 70, rewardXp: 70 },
  { title: "5 возражений за сессию", desc: "Набери 5+ обработанных возражений за одну сессию", type: "cold_call", minScore: 50, rewardXp: 60 },

  // ── Удержание и тёплые звонки ─────────────────────────────────
  { title: "Тёплый приём", desc: "Пройди сценарий тёплого звонка и набери 80+", type: "warm_call", minScore: 80, rewardXp: 50 },
  { title: "Удержание клиента", desc: "Убеди сомневающегося клиента остаться с нами", type: "retention", minScore: 70, rewardXp: 60 },
  { title: "Дополнительная продажа", desc: "Предложи дополнительную услугу и получи согласие", type: "warm_call", minScore: 65, rewardXp: 55 },

  // ── Стратегия и рост ──────────────────────────────────────────
  { title: "Выйди из зоны комфорта", desc: "Выбери сценарий сложности 7+ и набери хотя бы 60 баллов", type: "any", minScore: 60, rewardXp: 70 },
  { title: "Разведка боем", desc: "Попробуй совершенно новый для себя тип сценария", type: "any", minScore: 0, rewardXp: 40 },
  { title: "Прогресс на 10%", desc: "Улучши свой средний балл на 10% по сравнению с прошлой неделей", type: "any", minScore: 0, rewardXp: 80 },
  { title: "Точность формулировок", desc: "Набери 85%+ по параметру «Качество речи»", type: "cold_call", minScore: 85, rewardXp: 60 },

  // ── Арена и соревнования ──────────────────────────────────────
  { title: "Арена зовёт", desc: "Сыграй хотя бы один PvP-раунд в арене", type: "any", minScore: 0, rewardXp: 40 },
  { title: "Три победы", desc: "Одержи 3 победы в арене за сегодня", type: "any", minScore: 0, rewardXp: 70 },
  { title: "Знаток базы", desc: "Ответь правильно на 10 вопросов в Knowledge Arena", type: "any", minScore: 0, rewardXp: 50 },
  { title: "Командный дух", desc: "Помоги коллеге разобрать сложный сценарий (обсудите результаты)", type: "any", minScore: 0, rewardXp: 30 },
];

/**
 * Simple string hash to seed the challenge selection per user.
 */
function hashCode(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) {
    h = (Math.imul(31, h) + s.charCodeAt(i)) | 0;
  }
  return Math.abs(h);
}

/**
 * Returns today's challenge for a specific user.
 * Different users see different challenges on the same day.
 */
export function getDailyChallenge(userId?: string): DailyChallenge {
  const day = new Date();
  const dayOfYear = Math.floor(
    (day.getTime() - new Date(day.getFullYear(), 0, 0).getTime()) / 86_400_000,
  );
  const seed = userId ? hashCode(userId) : 0;
  const idx = (dayOfYear + seed) % CHALLENGES.length;
  return CHALLENGES[idx];
}
