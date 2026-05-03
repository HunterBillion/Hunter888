"use client";

/**
 * AutoBreadcrumbs — глобальные хлебные крошки, рендерятся на всех
 * authenticated-страницах через AuthLayout.
 *
 * 2026-04-20: добавлены массово после UX-аудита (старый Breadcrumb был
 * только на 9 из 57 страниц, на вложенных /training/[id]/call и
 * /methodologist/* пользователь терялся).
 *
 * Правила:
 *   • На корневых страницах (/home, /pvp, /training, /clients и т.д.)
 *     крошек нет — там хватает nav-активного таба.
 *   • На /section/[id] и /section/sub крошки автоматически строятся
 *     из pathname + LABEL_MAP (ручной перевод slug → человеческий
 *     заголовок на русском).
 *   • UUID'ы сокращаются до `#xxxxxxxx`, имя сессии при этом не
 *     подставляется — это ускорение без похода в store.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronRight } from "lucide-react";

const LABEL_MAP: Record<string, string> = {
  home: "Главная",
  training: "Тренировка",
  clients: "Клиенты",
  pipeline: "Воронка",
  graph: "Граф",
  pvp: "Арена",
  tournament: "Турнир",
  league: "Лига",
  teams: "Команды",
  team: "Команда",
  mistakes: "Ошибки",
  quiz: "Знания",
  duel: "Дуэль",
  arena: "Арена",
  rapid: "Скоростной бой",
  "rapid-fire": "Скоростной бой",
  gauntlet: "Испытание",
  spectate: "Наблюдение",
  lobby: "Лобби",
  call: "Звонок",
  results: "Результаты",
  history: "История",
  leaderboard: "Лидерборд",
  profile: "Профиль",
  settings: "Настройки",
  notifications: "Уведомления",
  stories: "Истории",
  dashboard: "Дашборд",
  // methodologist breadcrumb removed — /methodologist/* URLs deleted 2026-04-26
  scenarios: "Сценарии",
  "arena-content": "Контент Арены",
  scoring: "Скоринг",
  sessions: "Сессии",
  wiki: "Wiki",
  admin: "Админка",
  "audit-log": "Журнал аудита",
  archetypes: "Архетипы",
  crm: "CRM",
  onboarding: "Онбординг",
  consent: "Согласие",
  verify: "Проверка",
  reset_password: "Сброс пароля",
  change_password: "Смена пароля",
};

/** UUID v4 heuristic: 8-4-4-4-12 hex. */
function isUuid(part: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(part);
}

/** Short id to display when we can't resolve name. */
function shortId(part: string): string {
  return `#${part.slice(0, 8)}`;
}

export function AutoBreadcrumbs() {
  const pathname = usePathname() ?? "";
  const parts = pathname.split("/").filter(Boolean);

  // Root pages (/home, /pvp, /clients, ...) не нуждаются в крошках.
  if (parts.length < 2) return null;

  // Пути auth-flow (login/register) не проходят через AuthLayout — но
  // подстрахуемся: если вдруг pathname начинается с login — ничего не
  // рендерим.
  if (["login", "register", "forgot-password"].includes(parts[0])) return null;

  const items: { label: string; href?: string }[] = [];
  let current = "";
  for (let i = 0; i < parts.length; i++) {
    const part = parts[i];
    current += `/${part}`;
    const isLast = i === parts.length - 1;

    let label: string;
    if (isUuid(part)) {
      label = shortId(part);
    } else {
      label = LABEL_MAP[part] ?? part;
    }

    items.push({
      label,
      // Last crumb — not a link
      href: isLast ? undefined : current,
    });
  }

  return (
    <nav
      aria-label="Хлебные крошки"
      className="flex items-center gap-1.5 text-xs mb-3"
      style={{ color: "var(--text-muted)" }}
    >
      {items.map((item, i) => (
        <span key={i} className="flex items-center gap-1.5">
          {i > 0 && <ChevronRight size={12} className="opacity-40" aria-hidden />}
          {item.href ? (
            <Link
              href={item.href}
              prefetch={true}
              className="hover:underline transition-colors"
              style={{ color: "var(--text-muted)" }}
            >
              {item.label}
            </Link>
          ) : (
            <span style={{ color: "var(--text-primary)", fontWeight: 500 }}>
              {item.label}
            </span>
          )}
        </span>
      ))}
    </nav>
  );
}
