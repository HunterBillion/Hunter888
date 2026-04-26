"use client";

/**
 * MethodologyPanel — three sub-tabs for /dashboard "Методология":
 *   1. Методологи — list of methodologists scoped to the caller's team
 *      (ROP) or all teams (admin). Server enforces scope via
 *      apps/api/app/api/users.py::list_users.
 *   2. Wiki — corporate knowledge base, reuses <WikiDashboard>.
 *   3. Reviews — admin-only moderation queue, reuses <ReviewsAdmin>.
 *
 * Replaces the standalone "Wiki" and "Reviews" tabs in /dashboard so
 * the panel shape matches the owner's mental model: methodology stuff
 * lives in one place.
 */

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Mail } from "lucide-react";
import { BookOpen, Brain, Star } from "@phosphor-icons/react";
import dynamic from "next/dynamic";
import { api } from "@/lib/api";
import { roleName } from "@/lib/guards";
import { DashboardSkeleton } from "@/components/ui/Skeleton";

const WikiDashboard = dynamic(
  () => import("@/components/dashboard/WikiDashboard").then((m) => m.WikiDashboard),
  { loading: () => <DashboardSkeleton />, ssr: false }
);

const ReviewsAdmin = dynamic(
  () => import("@/components/dashboard/ReviewsAdmin").then((m) => m.ReviewsAdmin),
  { loading: () => <DashboardSkeleton />, ssr: false }
);

interface UserListItem {
  id: string;
  email: string;
  full_name: string;
  role: string;
  team_name: string | null;
  is_active: boolean;
  avatar_url: string | null;
  created_at: string;
}

type SubTab = "methodologists" | "wiki" | "reviews";

interface Props {
  isAdminCaller: boolean;
}

function MethodologistsList() {
  const [items, setItems] = useState<UserListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.get<UserListItem[]>("/users/?role=methodologist&limit=200")
      .then((data) => setItems(Array.isArray(data) ? data : []))
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Ошибка загрузки"))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <DashboardSkeleton />;
  if (error) {
    return (
      <div className="glass-panel rounded-xl p-6 text-center" style={{ color: "var(--danger)" }}>
        {error}
      </div>
    );
  }
  if (items.length === 0) {
    return (
      <div className="glass-panel rounded-xl p-8 text-center">
        <Brain size={32} weight="duotone" style={{ color: "var(--text-muted)", margin: "0 auto 12px", opacity: 0.5 }} />
        <p className="text-sm" style={{ color: "var(--text-muted)" }}>
          В вашей команде пока нет методологов. Назначить может администратор.
        </p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
      {items.map((u) => (
        <div
          key={u.id}
          className="glass-panel rounded-xl p-4 flex items-center gap-3"
          style={{ border: u.is_active ? "1px solid var(--border-color)" : "1px dashed var(--danger)" }}
        >
          <div
            className="flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center font-bold text-sm"
            style={{ background: "var(--accent-muted)", color: "var(--accent)" }}
          >
            {u.full_name.split(" ").map((p) => p[0]).slice(0, 2).join("").toUpperCase()}
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-sm font-semibold truncate" style={{ color: "var(--text-primary)" }}>
              {u.full_name}
            </div>
            <div className="flex items-center gap-2 text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
              <Mail size={12} />
              <span className="truncate">{u.email}</span>
            </div>
            <div className="flex items-center gap-2 text-xs mt-1" style={{ color: "var(--text-muted)" }}>
              <span>{roleName(u.role)}</span>
              {u.team_name && <span>· {u.team_name}</span>}
              {!u.is_active && <span style={{ color: "var(--danger)" }}>· неактивен</span>}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

const SUB_TABS: { id: SubTab; label: string; icon: typeof BookOpen; adminOnly?: boolean }[] = [
  { id: "methodologists", label: "Методологи", icon: Brain },
  { id: "wiki", label: "Wiki", icon: BookOpen },
  { id: "reviews", label: "Отзывы", icon: Star, adminOnly: true },
];

export function MethodologyPanel({ isAdminCaller }: Props) {
  const [active, setActive] = useState<SubTab>("methodologists");

  const visibleTabs = SUB_TABS.filter((t) => !t.adminOnly || isAdminCaller);

  return (
    <div className="space-y-4">
      {/* Sub-tab bar */}
      <div className="flex items-center gap-2 rounded-xl p-1.5" style={{ background: "var(--glass-bg)", border: "1px solid var(--glass-border)" }}>
        {visibleTabs.map((t) => {
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
              <Icon size={14} weight="duotone" style={{ color: isActive ? "var(--accent)" : undefined }} />
              <span>{t.label}</span>
              {isActive && (
                <motion.div
                  layoutId="methodology-subtab-indicator"
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
          {active === "methodologists" && <MethodologistsList />}
          {active === "wiki" && <WikiDashboard />}
          {active === "reviews" && isAdminCaller && <ReviewsAdmin />}
        </motion.div>
      </AnimatePresence>
    </div>
  );
}
