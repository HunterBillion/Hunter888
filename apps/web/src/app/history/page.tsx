"use client";

import { useEffect, useState, useMemo } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowRight } from "lucide-react";
import {
  Clock,
  CheckCircle,
  XCircle,
  Warning,
  Tray,
  ChartBar,
  Stack,
  Sparkle,
} from "@phosphor-icons/react";
import { Button } from "@/components/ui/Button";
import { api } from "@/lib/api";
import { scoreColor } from "@/lib/utils";
import AuthLayout from "@/components/layout/AuthLayout";
import type { HistoryEntry } from "@/types";

function statusConfig(status: string) {
  switch (status) {
    case "completed":
      return { label: "Завершено", icon: CheckCircle, color: "var(--success)" };
    case "abandoned":
      return { label: "Прервано", icon: XCircle, color: "var(--danger)" };
    case "error":
      return { label: "Ошибка", icon: Warning, color: "var(--warning)" };
    default:
      return { label: "Активно", icon: Clock, color: "var(--accent)" };
  }
}

function formatDuration(seconds: number | null) {
  if (seconds === null || seconds === undefined) return "—";
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function formatDate(iso: string) {
  const d = new Date(iso);
  return d.toLocaleDateString("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

// Mini score bars for breakdown
function MiniScoreBars({ session }: { session: HistoryEntry["latest_session"] }) {
  const bars = [
    { label: "Скр", value: session.score_script_adherence, max: 30, color: "var(--accent)" },
    { label: "Возр", value: session.score_objection_handling, max: 25, color: "var(--magenta)" },
    { label: "Ком", value: session.score_communication, max: 20, color: "var(--info)" },
    { label: "Рез", value: session.score_result, max: 10, color: "var(--success)" },
  ];

  return (
    <div className="flex gap-1 mt-2">
      {bars.map((bar) => {
        const pct = bar.value !== null && bar.max > 0 ? Math.round((bar.value / bar.max) * 100) : 0;
        return (
          <div key={bar.label} className="flex-1" title={`${bar.label}: ${bar.value ?? 0}/${bar.max}`}>
            <div className="h-1 rounded-full overflow-hidden" style={{ background: "var(--input-bg)" }}>
              <div className="h-full rounded-full" style={{ width: `${pct}%`, background: bar.color }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default function HistoryPage() {
  const router = useRouter();
  const [entries, setEntries] = useState<HistoryEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchHistory = () => {
    api
      .get("/training/history?limit=50")
      .then(setEntries)
      .catch((err) => setError(err.message || "Ошибка загрузки"))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchHistory();
  }, []);

  // Refetch sessions when user returns to the tab
  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === "visible") {
        fetchHistory();
      }
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, []);

  // Aggregate stats
  const latestSessions = entries.map((entry) => entry.latest_session);
  const completed = latestSessions.filter((s) => s.status === "completed");
  const avgScore = completed.length > 0
    ? Math.round(completed.reduce((sum, s) => sum + (s.score_total ?? 0), 0) / completed.length)
    : null;
  const storyCount = entries.filter((entry) => entry.kind === "story").length;

  // P2-19: Group sessions by date
  const groupedEntries = useMemo(() => {
    const now = new Date();
    const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
    const weekStart = todayStart - (now.getDay() === 0 ? 6 : now.getDay() - 1) * 86400000;

    const groups: { label: string; entries: HistoryEntry[] }[] = [
      { label: "Сегодня", entries: [] },
      { label: "На этой неделе", entries: [] },
      { label: "Ранее", entries: [] },
    ];

    for (const entry of entries) {
      const t = new Date(entry.sort_at).getTime();
      if (t >= todayStart) groups[0].entries.push(entry);
      else if (t >= weekStart) groups[1].entries.push(entry);
      else groups[2].entries.push(entry);
    }

    return groups.filter((g) => g.entries.length > 0);
  }, [entries]);

  return (
    <AuthLayout>
      <div className="relative panel-grid-bg min-h-screen">
        <div className="app-page max-w-4xl">
          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
            <h1 className="font-display text-2xl font-bold tracking-wider" style={{ color: "var(--text-primary)" }}>
              ИСТОРИЯ
            </h1>
            <p className="mt-1 text-sm" style={{ color: "var(--text-muted)" }}>
              Все ваши прошлые сессии
            </p>
          </motion.div>

          {/* Summary stats */}
          {!loading && entries.length > 0 && (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1 }}
              className="mt-6 grid grid-cols-2 gap-3 md:grid-cols-4"
            >
              {[
                { label: "Всего", value: entries.length, icon: ChartBar, color: "var(--accent)" },
                { label: "Историй", value: storyCount, icon: Stack, color: "var(--magenta)" },
                { label: "Завершено", value: completed.length, icon: CheckCircle, color: "var(--success)" },
                { label: "Ср. балл", value: avgScore !== null ? avgScore : "—", icon: Sparkle, color: "var(--warning)", hero: true },
              ].map((item) => {
                const Icon = item.icon;
                const isHero = "hero" in item && item.hero;
                return (
                  <div
                    key={item.label}
                    className="glass-panel p-4 text-center"
                    style={isHero ? { borderBottom: `2px solid ${item.color}` } : undefined}
                  >
                    <Icon size={isHero ? 18 : 14} weight="duotone" className="mx-auto mb-1" style={{ color: item.color }} />
                    <div className={`font-display font-bold ${isHero ? "text-2xl" : "text-xl"}`} style={{ color: isHero ? item.color : "var(--text-primary)" }}>{item.value}</div>
                    <div className="font-semibold text-xs uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>{item.label}</div>
                  </div>
                );
              })}
            </motion.div>
          )}

          {loading ? (
            <div className="mt-6 space-y-3">
              {[1, 2, 3, 4, 5].map((i) => (
                <div key={i} className="glass-panel p-5 flex items-center gap-4 animate-pulse">
                  <div className="w-10 h-10 rounded-xl bg-[var(--input-bg)]" />
                  <div className="flex-1 space-y-2">
                    <div className="flex gap-2">
                      <div className="h-3 w-16 rounded-full bg-[var(--input-bg)]" />
                      <div className="h-3 w-24 rounded bg-[var(--input-bg)]" />
                    </div>
                    <div className="h-2.5 w-20 rounded bg-[var(--input-bg)]" />
                    <div className="flex gap-1 mt-1">
                      {[1, 2, 3, 4].map((j) => (
                        <div key={j} className="flex-1 h-1 rounded-full bg-[var(--input-bg)]" />
                      ))}
                    </div>
                  </div>
                  <div className="h-8 w-12 rounded bg-[var(--input-bg)]" />
                </div>
              ))}
            </div>
          ) : error ? (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mt-16 flex flex-col items-center">
              <Warning size={40} weight="duotone" style={{ color: "var(--danger)" }} />
              <p className="mt-3 text-sm" style={{ color: "var(--danger)" }}>{error}</p>
            </motion.div>
          ) : entries.length === 0 ? (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mt-16 flex flex-col items-center">
              <Tray size={40} weight="duotone" style={{ color: "var(--text-muted)" }} />
              <p className="mt-3 text-sm" style={{ color: "var(--text-muted)" }}>Твоя история начнётся с первой тренировки.</p>
              <Button onClick={() => router.push("/training")} className="mt-4" iconRight={<ArrowRight size={16} />}>
                Начать первую охоту
              </Button>
            </motion.div>
          ) : (
            <div className="mt-6 space-y-6">
              {groupedEntries.map((group) => (
                <div key={group.label}>
                  <div className="flex items-center gap-3 mb-3">
                    <span className="font-semibold text-xs uppercase tracking-wide" style={{ color: "var(--accent)" }}>{group.label}</span>
                    <div className="flex-1 h-px" style={{ background: "var(--border-color)" }} />
                    <span className="font-mono text-xs" style={{ color: "var(--text-muted)" }}>{group.entries.length}</span>
                  </div>
                  <div className="space-y-3">
                    {group.entries.map((entry, i) => {
                      const session = entry.latest_session;
                      const st = statusConfig(session.status);
                      const Icon = st.icon;
                      const canViewResults = session.status === "completed" && session.score_total !== null;
                      const story = entry.story;
                      const targetHref = story ? `/training/crm/${story.id}` : `/results/${session.id}`;
                      const canOpenEntry = Boolean(story) || canViewResults;

                      return (
                        <motion.div
                          key={story?.id || session.id}
                          initial={{ opacity: 0, y: 12 }}
                          animate={{ opacity: 1, y: 0 }}
                          transition={{ delay: i * 0.04 }}
                          className={`glass-panel p-5 flex items-center gap-4 transition-all ${canOpenEntry ? "cursor-pointer" : ""}`}
                          style={{ boxShadow: `inset 3px 0 0 ${scoreColor(entry.avg_score ?? session.score_total)}` }}
                          whileHover={canOpenEntry ? { y: -2, boxShadow: "0 4px 20px rgba(139, 92, 246, 0.1)" } : undefined}
                          onClick={() => canOpenEntry && router.push(targetHref)}
                        >
                          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl" style={{ background: `color-mix(in srgb, ${st.color} 8%, transparent)` }}>
                            {story ? <Sparkle size={18} weight="duotone" style={{ color: "var(--accent)" }} /> : <Icon size={18} weight="duotone" style={{ color: st.color }} />}
                          </div>

                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="font-medium text-xs uppercase tracking-wide px-2 py-0.5 rounded-full inline-flex items-center gap-1" style={{ background: `color-mix(in srgb, ${story ? "var(--accent)" : st.color} 8%, transparent)`, color: story ? "var(--accent)" : st.color }}>
                                {story ? "AI Story" : st.label}
                              </span>
                              <span className="text-xs" style={{ color: "var(--text-muted)" }}>{formatDate(session.started_at)}</span>
                            </div>
                            <div className="mt-1 text-sm font-medium" style={{ color: "var(--text-primary)" }}>
                              {story ? story.story_name : "Одиночная тренировка"}
                            </div>
                            <div className="mt-1 flex items-center gap-4 text-xs" style={{ color: "var(--text-secondary)" }}>
                              <span className="flex items-center gap-1"><Clock size={12} weight="duotone" />{formatDuration(session.duration_seconds)}</span>
                              {story && (
                                <span>{story.completed_calls}/{story.total_calls_planned} звонков</span>
                              )}
                            </div>
                            {story && (
                              <div className="mt-2 flex flex-wrap gap-2">
                                <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                                  Статус: {story.game_status}
                                </span>
                                <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                                  Факторов: {story.active_factors.length}
                                </span>
                                <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                                  Последствий: {story.consequences.length}
                                </span>
                              </div>
                            )}
                            {canViewResults && <MiniScoreBars session={session} />}
                          </div>

                          <div className="text-right shrink-0">
                            {(entry.avg_score ?? session.score_total) !== null ? (
                              <div className="font-display text-2xl font-bold" style={{ color: scoreColor(entry.avg_score ?? session.score_total) }}>
                                {Math.round((entry.avg_score ?? session.score_total) as number)}
                                <span className="text-xs font-normal ml-0.5" style={{ color: "var(--text-muted)" }}>/100</span>
                              </div>
                            ) : (
                              <span className="text-xs" style={{ color: "var(--text-muted)" }}>—</span>
                            )}
                          </div>

                          {canOpenEntry && <ArrowRight size={16} style={{ color: "var(--text-muted)" }} />}
                        </motion.div>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </AuthLayout>
  );
}
