"use client";

/**
 * SystemPanel — admin-only "Система" tab inside /dashboard.
 * Two sub-tabs:
 *   1. Пользователи — full users registry (UsersAdminPanel)
 *   2. Client Domain — TZ-1 ops console (ClientDomainPanel)
 *
 * Gated at the /dashboard tab level (only rendered when caller is admin).
 * Sub-panels each handle their own loading/error states.
 */

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Activity, Database, Users as UsersIcon } from "lucide-react";
import dynamic from "next/dynamic";
import { DashboardSkeleton } from "@/components/ui/Skeleton";

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

type SubTab = "users" | "client_domain" | "runtime";

const SUB_TABS: { id: SubTab; label: string; icon: typeof UsersIcon }[] = [
  { id: "users", label: "Пользователи", icon: UsersIcon },
  // "Домен клиентов" = TZ-1 client_domain — operator-facing translation
  // of an architectural identifier. Sub-route param stays English so
  // existing deep-links don't break.
  { id: "client_domain", label: "Домен клиентов", icon: Database },
  { id: "runtime", label: "Среда выполнения", icon: Activity },
];

export function SystemPanel() {
  const [active, setActive] = useState<SubTab>("users");

  return (
    <div className="space-y-4">
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
              onClick={() => setActive(t.id)}
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
          {active === "client_domain" && <ClientDomainPanel />}
          {active === "runtime" && <RuntimeMetricsPanel />}
        </motion.div>
      </AnimatePresence>
    </div>
  );
}
