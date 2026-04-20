"use client";

/**
 * /admin — admin hub.
 *
 * Phase C (2026-04-20). До сих пор админ видел только `/admin/audit-log`
 * по прямой ссылке. Теперь это карточный хаб со всеми admin-surfaces.
 *
 * Endpoints backing each tile — все существуют на бэке:
 *   • /admin/audit-log        → GET /audit-log (admin-only)
 *   • /admin/health           → GET /health/detail (admin-only)  (опц.)
 *   • /admin/prompts          → prompts CRUD (methodologist+admin)
 * Карточки ведут на уже-существующие страницы. Страницы которых ещё нет
 * — помечены «Скоро».
 */

import Link from "next/link";
// 2026-04-20: AuthLayout теперь в admin/layout.tsx (общий на все admin-
// страницы, с таб-баром). Здесь обёртка убрана чтобы избежать двойного
// AuthLayout.
import {
  HeartPulse,
  Users,
  FlaskConical,
  FileText,
  ShieldAlert,
} from "lucide-react";

type IconComp = React.ComponentType<{ size?: number; style?: React.CSSProperties }>;

interface Tile {
  href: string;
  label: string;
  sub: string;
  icon: IconComp;
  available: boolean;
}

const TILES: Tile[] = [
  // Phase F (2026-04-20) — Audit card removed from hub. Owner feedback:
  // «в панели админка есть дубликация аудит». Журнал аудита теперь
  // доступен только через tab «Журнал аудита» в admin/layout.tsx —
  // ровно один вход, никакой путаницы между «перейти на отдельную
  // страницу» vs «кликнуть вкладку».
  {
    href: "/methodologist/scenarios",
    label: "Сценарии",
    sub: "CRUD сценариев тренировки",
    icon: FileText,
    available: true,
  },
  {
    href: "/methodologist/arena-content",
    label: "Контент Арены",
    sub: "Chunks правовых знаний",
    icon: FlaskConical,
    available: true,
  },
  {
    href: "/methodologist/sessions",
    label: "Сессии (browse)",
    sub: "Все сессии юзеров для ревью",
    icon: Users,
    available: true,
  },
  {
    href: "/admin/health",
    label: "Здоровье системы",
    sub: "Health-check + метрики",
    icon: HeartPulse,
    available: false,
  },
  {
    href: "/admin/prompts",
    label: "Промпты",
    sub: "Versioned prompts CRUD",
    icon: ShieldAlert,
    available: false,
  },
];

export default function AdminHubPage() {
  // 2026-04-20: показываем только доступные разделы. Плитки со "скоро"
  // раньше выглядели как рабочие, но не кликались — пользователи жаловались
  // "панель выглядит нерабочей". Неготовые разделы добавим обратно когда
  // страницы реально появятся.
  const availableTiles = TILES.filter((t) => t.available);
  return (
    <>
      <div className="max-w-4xl">
        <p
          className="text-sm mb-5 max-w-2xl"
          style={{ color: "var(--text-muted)" }}
        >
          Полный доступ ко всему: 152-ФЗ аудит, контент-инструменты методолога,
          системные метрики. Эта страница видна только роли{" "}
          <code>admin</code>.
        </p>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {availableTiles.map((t) => {
            const Icon = t.icon;
            const Inner = (
              <>
                <div className="flex items-center gap-3 mb-2">
                  <div
                    className="flex h-10 w-10 items-center justify-center rounded-xl"
                    style={{
                      background: "#fbbf2418",
                      color: "#fbbf24",
                      border: "1px solid #fbbf2444",
                    }}
                  >
                    <Icon size={18} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div
                      className="text-[13px] font-semibold"
                      style={{ color: "var(--text-primary)" }}
                    >
                      {t.label}
                    </div>
                    {!t.available && (
                      <span
                        className="text-[9px] uppercase tracking-widest"
                        style={{ color: "var(--text-muted)" }}
                      >
                        скоро
                      </span>
                    )}
                  </div>
                </div>
                <p
                  className="text-[12px] leading-relaxed"
                  style={{ color: "var(--text-muted)" }}
                >
                  {t.sub}
                </p>
              </>
            );
            return (
              <Link
                key={t.href}
                href={t.href}
                className="rounded-xl p-4 transition-all hover:-translate-y-0.5 hover:shadow-lg"
                style={{
                  background: "var(--bg-panel)",
                  border: "1px solid #fbbf2433",
                }}
              >
                {Inner}
              </Link>
            );
          })}
        </div>
      </div>
    </>
  );
}
