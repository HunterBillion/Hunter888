import type { LeadSource, LeadSourceGroup } from "@/types";

export interface LeadSourceInfo {
  code: LeadSource;
  name: string;
  group: LeadSourceGroup;
  trust: number;       // -2 to +3
  awareness: number;   // 0-3
  description: string;
}

export interface LeadSourceGroupInfo {
  label: string;
  sources: LeadSource[];
}

export const LEAD_SOURCE_GROUPS: Record<LeadSourceGroup, LeadSourceGroupInfo> = {
  cold: { label: "Холодные", sources: ["cold_base", "cold_social", "cold_event"] },
  warm: { label: "Тёплые", sources: ["website_form", "social_media", "webinar", "warm_complaint", "warm_competitor", "lead_nurture", "ad_retarget"] },
  inbound: { label: "Входящие", sources: ["incoming", "in_chat", "chatbot", "in_referral_direct", "in_urgent"] },
  repeat: { label: "Повторные", sources: ["referral", "repeat_call", "partner", "churned", "callback_scheduled"] },
};

export const LEAD_SOURCES: LeadSourceInfo[] = [
  // ── Холодные ──
  { code: "cold_base", name: "Холодная база", group: "cold", trust: -2, awareness: 0, description: "Звонок по базе. Клиент не ожидал, раздражён." },
  { code: "cold_social", name: "Соцсети (хол.)", group: "cold", trust: -1, awareness: 1, description: "Написали в ЛС. Видел рекламу, но не проявлял интерес." },
  { code: "cold_event", name: "Мероприятие", group: "cold", trust: 0, awareness: 1, description: "Контакт с выставки/семинара. Оставил визитку." },
  // ── Тёплые ──
  { code: "website_form", name: "Заявка с сайта", group: "warm", trust: 1, awareness: 2, description: "Клиент сам оставил заявку. Активный интерес." },
  { code: "social_media", name: "Соцсети (тёпл.)", group: "warm", trust: 0, awareness: 1, description: "Подписчик, комментировал посты." },
  { code: "webinar", name: "Вебинар", group: "warm", trust: 2, awareness: 2, description: "Участвовал в онлайн-семинаре 30-60 мин." },
  { code: "warm_complaint", name: "Жалоба", group: "warm", trust: 0, awareness: 0, description: "Пожаловался на коллекторов/банк, перенаправлен." },
  { code: "warm_competitor", name: "От конкурента", group: "warm", trust: -1, awareness: 3, description: "Ушёл от другой компании, разочарован." },
  { code: "lead_nurture", name: "Прогретый", group: "warm", trust: 1, awareness: 2, description: "Подписан на рассылку, читал статьи." },
  { code: "ad_retarget", name: "Ретаргетинг", group: "warm", trust: 0, awareness: 1, description: "Видел рекламу после визита сайта." },
  // ── Входящие ──
  { code: "incoming", name: "Входящий", group: "inbound", trust: 2, awareness: 2, description: "Клиент сам позвонил. Максимальная готовность." },
  { code: "in_chat", name: "Чат на сайте", group: "inbound", trust: 1, awareness: 1, description: "Написал в чат-виджет. Предпочитает текст." },
  { code: "chatbot", name: "Чат-бот", group: "inbound", trust: 1, awareness: 1, description: "Общался с ботом, бот передал менеджеру." },
  { code: "in_referral_direct", name: "Прямая рекомендация", group: "inbound", trust: 3, awareness: 2, description: "Знакомый лично передал контакт." },
  { code: "in_urgent", name: "Срочный входящий", group: "inbound", trust: 1, awareness: 1, description: "Звонит в панике — завтра суд/приставы." },
  // ── Повторные ──
  { code: "referral", name: "Рекомендация", group: "repeat", trust: 2, awareness: 1, description: "Пришёл по отзыву или совету знакомого." },
  { code: "repeat_call", name: "Повторный", group: "repeat", trust: 0, awareness: 2, description: "Уже звонил ранее, возвращается." },
  { code: "partner", name: "Партнёр", group: "repeat", trust: 1, awareness: 1, description: "Перенаправлен от МФО/банка/партнёра." },
  { code: "churned", name: "Отвалившийся", group: "repeat", trust: -1, awareness: 3, description: "Бывший клиент, отказался, вернулся." },
  { code: "callback_scheduled", name: "Запланированный", group: "repeat", trust: 2, awareness: 2, description: "Сам назначил время звонка." },
];

export function findLeadSource(code: string): LeadSourceInfo | undefined {
  return LEAD_SOURCES.find((s) => s.code === code);
}
