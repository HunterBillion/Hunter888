/**
 * categories.ts — единый источник правды для перевода ФЗ-127 категорий
 * с code (английский enum) → label (русский human-readable).
 *
 * До PR-13 этот маппинг существовал в 3 местах независимо:
 *   - HonestNavigator.tsx (10 чипов)
 *   - ArenaContentEditor.tsx (RoP CRUD)
 *   - apps/api/app/api/knowledge.py CATEGORY_DISPLAY_NAMES (бэк)
 *
 * А в quiz/[sessionId]/page.tsx и в side-aside `aside header` коды
 * шли сырыми → юзер видел «property», «timeline» вместо «Имущество»,
 * «Сроки» (P0 баг из аудита).
 */

export const CATEGORY_LABELS: Record<string, string> = {
  eligibility: "Условия подачи",
  procedure: "Порядок процедуры",
  property: "Имущество",
  consequences: "Последствия",
  costs: "Расходы",
  creditors: "Кредиторы",
  documents: "Документы",
  timeline: "Сроки",
  court: "Суд",
  rights: "Права должника",
  // Legacy / extra codes seen on prod:
  general: "Общие вопросы",
  discharge: "Освобождение от долгов",
  trustee: "Финансовый управляющий",
};

export function categoryLabel(code: string | null | undefined): string {
  if (!code) return "—";
  return CATEGORY_LABELS[code] ?? code;
}
