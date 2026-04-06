import type { ProfessionCategory, ProfessionGroup } from "@/types";

export interface ProfessionInfo {
  code: ProfessionCategory;
  name: string;
  icon: string;
  debtRange: string;
  incomeRange: string;
  group: ProfessionGroup;
  oceanMod: { O?: number; C?: number; E?: number; A?: number; N?: number };
  formality: number; // 0-1
}

export interface ProfessionGroupInfo {
  label: string;
  professions: ProfessionCategory[];
}

export const PROFESSION_GROUPS: Record<ProfessionGroup, ProfessionGroupInfo> = {
  budget_gov: { label: "Бюджет и государство", professions: ["budget", "government", "medical", "education"] },
  military_law: { label: "Силовые структуры", professions: ["military", "law_enforcement"] },
  business: { label: "Бизнес и финансы", professions: ["entrepreneur", "finance", "freelancer"] },
  workers: { label: "Рабочие специальности", professions: ["worker", "construction", "transport", "agriculture"] },
  intellectual: { label: "IT и интеллектуальные", professions: ["it_office", "science", "creative"] },
  trade_sport: { label: "Торговля и спорт", professions: ["trade_service", "sports"] },
  special_cat: { label: "Особые категории", professions: ["pensioner", "homemaker", "student", "unemployed", "disabled", "clergy", "special"] },
};

export const PROFESSIONS: ProfessionInfo[] = [
  // ── Бюджет и государство ──
  { code: "budget", name: "Бюджетник", icon: "\u{1F3DB}\uFE0F", debtRange: "100K\u20131M", incomeRange: "25\u201355K", group: "budget_gov", oceanMod: { C: 0.10, A: 0.05 }, formality: 0.5 },
  { code: "government", name: "Госслужащий", icon: "\u{1F3E2}", debtRange: "200K\u20132M", incomeRange: "35\u201380K", group: "budget_gov", oceanMod: { C: 0.15, O: -0.05 }, formality: 0.8 },
  { code: "medical", name: "Медработник", icon: "\u{1F3E5}", debtRange: "150K\u20131.5M", incomeRange: "25\u201370K", group: "budget_gov", oceanMod: { A: 0.15, N: 0.10 }, formality: 0.5 },
  { code: "education", name: "Педагог", icon: "\u{1F4DA}", debtRange: "100K\u2013800K", incomeRange: "20\u201350K", group: "budget_gov", oceanMod: { O: 0.10, A: 0.10, C: 0.05 }, formality: 0.7 },
  // ── Силовые ──
  { code: "military", name: "Военный", icon: "\u{1F396}\uFE0F", debtRange: "150K\u20131.5M", incomeRange: "40\u201390K", group: "military_law", oceanMod: { C: 0.20, A: -0.10, E: -0.05 }, formality: 0.8 },
  { code: "law_enforcement", name: "Силовик", icon: "\u{1F46E}", debtRange: "200K\u20132M", incomeRange: "35\u201385K", group: "military_law", oceanMod: { C: 0.15, A: -0.15, N: -0.05 }, formality: 0.8 },
  // ── Бизнес ──
  { code: "entrepreneur", name: "Предприниматель", icon: "\u{1F4BC}", debtRange: "500K\u20135M", incomeRange: "30\u2013200K", group: "business", oceanMod: { E: 0.10, O: 0.10, C: 0.05 }, formality: 0.5 },
  { code: "finance", name: "Финансист", icon: "\u{1F4B9}", debtRange: "300K\u20133M", incomeRange: "40\u2013120K", group: "business", oceanMod: { C: 0.20, O: -0.05, A: -0.05 }, formality: 0.8 },
  { code: "freelancer", name: "Фрилансер", icon: "\u{1F4BB}", debtRange: "100K\u20132M", incomeRange: "15\u2013150K", group: "business", oceanMod: { O: 0.15, C: -0.10, E: 0.05 }, formality: 0.3 },
  // ── Рабочие ──
  { code: "worker", name: "Рабочий", icon: "\u{1F527}", debtRange: "100K\u2013800K", incomeRange: "25\u201360K", group: "workers", oceanMod: { C: 0.05, O: -0.10, A: 0.05 }, formality: 0.3 },
  { code: "construction", name: "Строитель", icon: "\u{1F3D7}\uFE0F", debtRange: "150K\u20131.5M", incomeRange: "30\u201380K", group: "workers", oceanMod: { C: 0.05, A: -0.05, E: 0.05 }, formality: 0.3 },
  { code: "transport", name: "Транспорт", icon: "\u{1F69A}", debtRange: "100K\u20131M", incomeRange: "25\u201370K", group: "workers", oceanMod: { E: 0.05, C: -0.05, N: 0.05 }, formality: 0.3 },
  { code: "agriculture", name: "Сельское хоз.", icon: "\u{1F33E}", debtRange: "100K\u20131M", incomeRange: "15\u201350K", group: "workers", oceanMod: { C: 0.10, O: -0.15, A: 0.05 }, formality: 0.2 },
  // ── IT и интеллектуальные ──
  { code: "it_office", name: "IT / Офис", icon: "\u{1F4BB}", debtRange: "300K\u20133M", incomeRange: "60\u2013250K", group: "intellectual", oceanMod: { O: 0.10, C: 0.10, E: -0.05 }, formality: 0.5 },
  { code: "science", name: "Наука", icon: "\u{1F52C}", debtRange: "100K\u20131M", incomeRange: "20\u201360K", group: "intellectual", oceanMod: { O: 0.20, C: 0.10, E: -0.10 }, formality: 0.8 },
  { code: "creative", name: "Творческая", icon: "\u{1F3A8}", debtRange: "100K\u20131M", incomeRange: "10\u201380K", group: "intellectual", oceanMod: { O: 0.25, C: -0.15, E: 0.10, N: 0.10 }, formality: 0.3 },
  // ── Торговля и спорт ──
  { code: "trade_service", name: "Торговля/Сервис", icon: "\u{1F6D2}", debtRange: "100K\u20131M", incomeRange: "20\u201380K", group: "trade_sport", oceanMod: { E: 0.10, A: 0.05 }, formality: 0.4 },
  { code: "sports", name: "Спорт", icon: "\u26BD", debtRange: "100K\u20132M", incomeRange: "15\u2013100K", group: "trade_sport", oceanMod: { C: 0.15, E: 0.15, A: -0.05 }, formality: 0.3 },
  // ── Особые категории ──
  { code: "pensioner", name: "Пенсионер", icon: "\u{1F474}", debtRange: "50K\u2013500K", incomeRange: "12\u201325K", group: "special_cat", oceanMod: { C: 0.10, O: -0.10, N: 0.10 }, formality: 0.5 },
  { code: "homemaker", name: "Домохозяйка", icon: "\u{1F3E0}", debtRange: "50K\u2013500K", incomeRange: "0\u201325K", group: "special_cat", oceanMod: { A: 0.15, C: -0.05, N: 0.10 }, formality: 0.3 },
  { code: "student", name: "Студент", icon: "\u{1F393}", debtRange: "50K\u2013500K", incomeRange: "0\u201325K", group: "special_cat", oceanMod: { O: 0.15, C: -0.10, E: 0.10 }, formality: 0.3 },
  { code: "unemployed", name: "Безработный", icon: "\u{1F4AD}", debtRange: "100K\u20131M", incomeRange: "0\u201315K", group: "special_cat", oceanMod: { N: 0.15, C: -0.10, E: -0.10 }, formality: 0.3 },
  { code: "disabled", name: "Инвалид", icon: "\u267F", debtRange: "50K\u2013800K", incomeRange: "10\u201330K", group: "special_cat", oceanMod: { N: 0.10, A: 0.05, E: -0.10 }, formality: 0.5 },
  { code: "clergy", name: "Духовенство", icon: "\u271D\uFE0F", debtRange: "100K\u2013500K", incomeRange: "15\u201340K", group: "special_cat", oceanMod: { A: 0.20, C: 0.15, O: 0.05, N: -0.05 }, formality: 0.8 },
  { code: "special", name: "Другое", icon: "\u2728", debtRange: "100K\u20132M", incomeRange: "30\u2013100K", group: "special_cat", oceanMod: {}, formality: 0.5 },
];

export function findProfession(code: string): ProfessionInfo | undefined {
  return PROFESSIONS.find((p) => p.code === code);
}
