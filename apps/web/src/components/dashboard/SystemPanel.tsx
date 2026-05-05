"use client";

/**
 * SystemPanel — admin-only "Система" tab inside /dashboard.
 * Three sub-tabs:
 *   1. users   — full users registry (UsersAdminPanel)
 *   2. events  — CRM events / parity console (was `client_domain`,
 *                renamed 2026-05-05 because the operator-facing label
 *                "Домен клиентов" leaked an architectural identifier).
 *   3. health  — runtime metrics (was `runtime`).
 *
 * Legacy URL ids (`client_domain`, `runtime`) are normalised on read so
 * existing bookmarks land on the right place without a 404 flicker.
 *
 * Gated at the /dashboard tab level (only rendered when caller is admin).
 * Sub-panels each handle their own loading/error states.
 */

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Activity, Database, Users as UsersIcon } from "lucide-react";
import dynamic from "next/dynamic";
import { useSearchParams } from "next/navigation";
import { DashboardSkeleton } from "@/components/ui/Skeleton";
import { PixelInfoButton } from "@/components/ui/PixelInfoButton";
import { type SystemSubTab, resolveSystemSub } from "@/lib/dashboard-tabs";

const UsersAdminPanel = dynamic(
  () => import("@/components/dashboard/UsersAdminPanel").then((m) => m.UsersAdminPanel),
  { loading: () => <DashboardSkeleton />, ssr: false }
);

const ClientDomainPanel = dynamic(
  () => import("@/components/dashboard/ClientDomainPanel").then((m) => m.ClientDomainPanel),
  { loading: () => <DashboardSkeleton />, ssr: false }
);

const RuntimeMetricsPanel = dynamic(
  () => import("@/components/dashboard/RuntimeMetricsPanel").then((m) => m.RuntimeMetricsPanel),
  { loading: () => <DashboardSkeleton />, ssr: false }
);

// SystemSubTab + SYSTEM_SUB_ALIASES + resolveSystemSub live in
// lib/dashboard-tabs.ts so they can be unit-tested without React.
type SubTab = SystemSubTab;

const SUB_TABS: { id: SubTab; label: string; icon: typeof UsersIcon }[] = [
  { id: "users", label: "Пользователи", icon: UsersIcon },
  // Was "Домен клиентов" (`client_domain`) — leaked an architectural
  // identifier. The panel itself is the parity / events console, so
  // the user-facing label says so.
  { id: "events", label: "События клиентов", icon: Database },
  // Was "Среда выполнения" (`runtime`) — engineering jargon. From the
  // owner's POV this is the service-health dashboard.
  { id: "health", label: "Здоровье сервиса", icon: Activity },
];

export function SystemPanel() {
  const searchParams = useSearchParams();

  const rawSub = searchParams.get("sub");
  const initialSub = resolveSystemSub(rawSub);

  const [active, setActive] = useState<SubTab>(initialSub);

  useEffect(() => {
    setActive(initialSub);
    // Rewrite legacy / garbage ids in the address bar so the URL
    // matches what's shown — saves the user from re-bookmarking later.
    // Note: window.history.replaceState() does NOT trigger a Next.js
    // App Router re-render of useSearchParams (verified in Next 14/15),
    // so this loop is bounded — `rawSub` won't change as a result of
    // our own write.
    const needsRewrite = rawSub !== null && rawSub !== initialSub;
    if (needsRewrite && typeof window !== "undefined") {
      const url = new URL(window.location.href);
      url.searchParams.set("sub", initialSub);
      window.history.replaceState(null, "", url.toString());
    }
  }, [initialSub, rawSub]);


  const switchSub = (id: SubTab) => {
    setActive(id);
    if (typeof window !== "undefined") {
      const url = new URL(window.location.href);
      url.searchParams.set("sub", id);
      window.history.replaceState(null, "", url.toString());
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="font-display text-base tracking-wider" style={{ color: "var(--text-secondary)" }}>
          СИСТЕМА
        </h2>
        <PixelInfoButton
          title="Система"
          sections={[
            { icon: UsersIcon, label: "Пользователи", text: "Полный реестр аккаунтов: создать, заблокировать, сменить роль, сбросить пароль. Только admin." },
            { icon: Database, label: "События клиентов", text: "Оперативный пульт по событиям CRM: согласованность данных, последние 50 событий, переключатели путей записи." },
            { icon: Activity, label: "Здоровье сервиса", text: "Счётчики выполнения сессий: сколько завершилось через WS, сколько через REST, сколько защит сработало, сколько задач на повторный звонок не создалось." },
          ]}
          footer="Только для admin. РОП видит «Команду» и «Аудит-журнал», но не «Систему»."
        />
      </div>
      <div
        className="flex items-center gap-2 rounded-xl p-1.5"
        style={{ background: "var(--glass-bg)", border: "1px solid var(--glass-border)" }}
      >
        {SUB_TABS.map((t) => {
          const Icon = t.icon;
          const isActive = active === t.id;
          return (
            <button
              key={t.id}
              onClick={() => switchSub(t.id)}
              className="relative flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors"
              style={{
                color: isActive ? "var(--text-primary)" : "var(--text-muted)",
                fontWeight: isActive ? 600 : 500,
              }}
            >
              <Icon size={14} style={{ color: isActive ? "var(--accent)" : undefined }} />
              <span>{t.label}</span>
              {isActive && (
                <motion.div
                  layoutId="system-subtab-indicator"
                  className="absolute inset-0 rounded-lg -z-10"
                  style={{ background: "var(--accent-muted)", border: "1px solid var(--accent)" }}
                  transition={{ type: "spring", stiffness: 400, damping: 30 }}
                />
              )}
            </button>
          );
        })}
      </div>

      <AnimatePresence mode="wait">
        <motion.div
          key={active}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
        >
          {active === "users" && <UsersAdminPanel />}
          {active === "events" && <ClientDomainPanel />}
          {active === "health" && <RuntimeMetricsPanel />}
        </motion.div>
      </AnimatePresence>
    </div>
  );
}
