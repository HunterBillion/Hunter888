"use client";

/**
 * /dashboard/team/[id] — methodologist-style deep dive on one team member.
 *
 * Backed by GET /dashboard/team/member/{member_id} which bundles:
 *   - basic info
 *   - completed-session stats (total/avg/best/this-week)
 *   - composite behavior + OCEAN
 *   - top-5 weak spots with trend + recommendation
 *   - last 10 sessions
 *
 * Permissions: admin can open any user; ROP only own-team members
 * (server enforces 403). Manager / methodologist do not see this route
 * at all (the hub /dashboard already gates them out).
 */

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowLeft, TrendingUp, TrendingDown, Minus } from "lucide-react";
import { Clock, ShieldWarning, Target } from "@phosphor-icons/react";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { isManager, roleName } from "@/lib/guards";
import AuthLayout from "@/components/layout/AuthLayout";
import { DashboardSkeleton } from "@/components/ui/Skeleton";
import { ScoreBadge } from "@/components/ui/ScoreBadge";
import BehaviorProfileCard from "@/components/behavior/BehaviorProfileCard";
import { OceanProfileWidget } from "@/components/dashboard/OceanProfileWidget";
import { logger } from "@/lib/logger";

interface MemberBundle {
  member: {
    id: string;
    full_name: string;
    email: string;
    role: string;
    team_id: string | null;
    team_name: string | null;
    is_active: boolean;
  };
  stats: {
    total_sessions: number;
    avg_score: number;
    best_score: number;
    sessions_this_week: number;
  };
  behavior: {
    composite: {
      confidence: number;
      stress_resistance: number;
      adaptability: number;
      empathy: number;
    };
    performance: {
      under_hostility: number | null;
      under_stress: number | null;
      with_empathy: number | null;
    };
    archetype_scores: Record<string, number>;
    sessions_analyzed: number;
  };
  ocean: unknown;
  weak_spots: Array<{
    skill: string;
    sub_skill: string | null;
    pct: number;
    trend: string;
    trend_delta: number;
    archetype: string | null;
    recommendation: string;
  }>;
  recent_sessions: Array<{
    id: string;
    scenario_id: string | null;
    score_total: number;
    duration_seconds: number | null;
    started_at: string | null;
  }>;
}

function StatTile({ label, value, accent = "var(--accent)" }: { label: string; value: string | number; accent?: string }) {
  return (
    <div className="rounded-xl p-4" style={{ background: "var(--bg-panel)", border: "1px solid var(--border-color)" }}>
      <div className="text-[11px] uppercase tracking-wider mb-1 font-semibold" style={{ color: "var(--text-muted)" }}>{label}</div>
      <div className="text-2xl font-bold" style={{ color: accent }}>{value}</div>
    </div>
  );
}

function TrendIcon({ trend }: { trend: string }) {
  if (trend === "improving") return <TrendingUp size={14} style={{ color: "var(--success)" }} />;
  if (trend === "declining") return <TrendingDown size={14} style={{ color: "var(--danger)" }} />;
  return <Minus size={14} style={{ color: "var(--text-muted)" }} />;
}

function formatDuration(s: number | null): string {
  if (!s) return "—";
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return `${m}:${sec.toString().padStart(2, "0")}`;
}

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
  } catch {
    return iso;
  }
}

export default function TeamMemberDeepDivePage() {
  const params = useParams();
  const router = useRouter();
  const { user } = useAuth();
  const memberId = typeof params.id === "string" ? params.id : String(params.id ?? "");

  const [bundle, setBundle] = useState<MemberBundle | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;
    if (!isManager(user)) {
      setError("Доступ ограничен");
      setLoading(false);
      return;
    }
    api.get<MemberBundle>(`/dashboard/team/member/${memberId}`)
      .then((data) => setBundle(data))
      .catch((err: unknown) => {
        const msg = err instanceof ApiError
          ? (err.status === 403 ? "Этот пользователь не из вашей команды" : err.message)
          : err instanceof Error ? err.message : "Ошибка загрузки";
        setError(msg);
        logger.error("[TeamMemberDeepDive] Failed:", err);
      })
      .finally(() => setLoading(false));
  }, [user, memberId]);

  return (
    <AuthLayout>
      <div className="mx-auto max-w-6xl px-4 py-6 space-y-6">
        {/* ── Back ──────────────────────────────────────────────────── */}
        <Link
          href="/dashboard"
          className="inline-flex items-center gap-2 text-sm font-medium hover:underline"
          style={{ color: "var(--text-muted)" }}
        >
          <ArrowLeft size={14} />
          К команде
        </Link>

        {loading && <DashboardSkeleton />}

        {!loading && error && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mt-12 flex flex-col items-center">
            <ShieldWarning size={40} style={{ color: "var(--danger)" }} />
            <p className="mt-3 text-sm" style={{ color: "var(--danger)" }}>{error}</p>
          </motion.div>
        )}

        {!loading && bundle && (
          <>
            {/* ── Header: name, role, team ─────────────────────────── */}
            <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }}>
              <div className="flex items-center gap-3">
                <h1 className="font-display text-3xl font-bold tracking-wider" style={{ color: "var(--text-primary)" }}>
                  {bundle.member.full_name}
                </h1>
                {!bundle.member.is_active && (
                  <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: "var(--danger-muted)", color: "var(--danger)" }}>
                    Неактивен
                  </span>
                )}
              </div>
              <p className="mt-2 text-sm" style={{ color: "var(--text-muted)" }}>
                {roleName(bundle.member.role)}
                {bundle.member.team_name ? ` · команда «${bundle.member.team_name}»` : " · без команды"}
                {" · "}{bundle.member.email}
              </p>
            </motion.div>

            {/* ── Stats row ────────────────────────────────────────── */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <StatTile label="Всего сессий" value={bundle.stats.total_sessions} />
              <StatTile label="Средний балл" value={bundle.stats.avg_score || "—"} accent="var(--success)" />
              <StatTile label="Лучший" value={bundle.stats.best_score || "—"} accent="var(--warning)" />
              <StatTile label="За неделю" value={bundle.stats.sessions_this_week} accent="var(--accent)" />
            </div>

            {/* ── Behavior + OCEAN ─────────────────────────────────── */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <BehaviorProfileCard userId={bundle.member.id} />
              <OceanProfileWidget initialData={bundle.ocean as Parameters<typeof OceanProfileWidget>[0] extends { initialData?: infer T } ? T : never} />
            </div>

            {/* ── Weak spots ───────────────────────────────────────── */}
            <div className="glass-panel rounded-xl p-5">
              <div className="flex items-center gap-2 mb-3">
                <Target size={16} weight="duotone" style={{ color: "var(--danger)" }} />
                <h2 className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--danger)" }}>
                  Слабые места ({bundle.weak_spots.length})
                </h2>
              </div>
              {bundle.weak_spots.length === 0 ? (
                <p className="text-sm italic" style={{ color: "var(--text-muted)" }}>
                  Недостаточно данных для анализа — менее 5 завершённых сессий.
                </p>
              ) : (
                <ul className="space-y-3">
                  {bundle.weak_spots.map((w, i) => (
                    <li key={`${w.skill}-${i}`} className="rounded-lg p-3" style={{ background: "var(--bg-panel)", border: "1px solid var(--border-color)" }}>
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-sm" style={{ color: "var(--text-primary)" }}>{w.skill}</span>
                          {w.sub_skill && <span className="text-xs" style={{ color: "var(--text-muted)" }}>· {w.sub_skill}</span>}
                          {w.archetype && <span className="text-xs px-1.5 py-0.5 rounded" style={{ background: "var(--accent-muted)", color: "var(--accent)" }}>{w.archetype}</span>}
                        </div>
                        <div className="flex items-center gap-2">
                          <TrendIcon trend={w.trend} />
                          <ScoreBadge score={w.pct} />
                        </div>
                      </div>
                      <p className="text-xs mt-1.5" style={{ color: "var(--text-secondary)" }}>{w.recommendation}</p>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {/* ── Recent sessions ──────────────────────────────────── */}
            <div className="glass-panel rounded-xl p-5">
              <div className="flex items-center gap-2 mb-3">
                <Clock size={16} weight="duotone" style={{ color: "var(--accent)" }} />
                <h2 className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--accent)" }}>
                  Последние сессии ({bundle.recent_sessions.length})
                </h2>
              </div>
              {bundle.recent_sessions.length === 0 ? (
                <p className="text-sm italic" style={{ color: "var(--text-muted)" }}>Сессий ещё нет.</p>
              ) : (
                <ul className="divide-y" style={{ borderColor: "var(--border-color)" }}>
                  {bundle.recent_sessions.map((s) => (
                    <li key={s.id} className="py-2.5 flex items-center justify-between gap-3">
                      <div className="flex-1 min-w-0">
                        <Link href={`/results/${s.id}`} className="text-sm font-medium hover:underline" style={{ color: "var(--text-primary)" }}>
                          Сессия от {formatDate(s.started_at)}
                        </Link>
                        <div className="text-xs" style={{ color: "var(--text-muted)" }}>
                          Длительность: {formatDuration(s.duration_seconds)}
                        </div>
                      </div>
                      <ScoreBadge score={s.score_total} />
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </>
        )}
      </div>
    </AuthLayout>
  );
}
