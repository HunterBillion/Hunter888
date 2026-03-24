"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { motion } from "framer-motion";
import {
  Clock,
  ArrowRight,
  Home,
  MessageSquare,
  TrendingDown,
  TrendingUp,
  Loader2,
  AlertCircle,
  AlertTriangle,
  CheckCircle,
  RotateCcw,
  Crosshair,
  Repeat,
    Share2,
    Check,
    Trophy,
    Download,
    Copy,
    ClipboardCheck,
    Swords,
    Crown,
    Medal,
    Layers3,
    Sparkles,
  } from "lucide-react";
import { api } from "@/lib/api";
import { downloadTranscript, copyTranscript } from "@/lib/exportTranscript";
import AuthLayout from "@/components/layout/AuthLayout";
import { PageSkeleton } from "@/components/ui/Skeleton";
import PentagramChart from "@/components/results/PentagramChart";
import EmotionTimeline from "@/components/results/EmotionTimeline";
import TrapResults from "@/components/results/TrapResults";
import SoftSkillsCard from "@/components/results/SoftSkillsCard";
import ClientReveal from "@/components/results/ClientReveal";
import AIRecommendations from "@/components/results/AIRecommendations";
import CheckpointProgress from "@/components/results/CheckpointProgress";
import { AchievementToast } from "@/components/gamification/AchievementToast";
import { EMOTION_MAP, type EmotionState, type SessionResultResponse, type ActiveTournamentResponse, type TournamentSubmitResponse } from "@/types";

function formatDuration(seconds: number | null): string {
  if (!seconds) return "--:--";
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return m > 0 ? `${m} мин ${s} сек` : `${s} сек`;
}

const stateValues: Record<string, number> = { cold: 0, skeptical: 1, warming: 2, open: 3, deal: 4 };

function emotionColor(state: string): string {
  return EMOTION_MAP[state as EmotionState]?.color ?? "var(--text-muted)";
}

function emotionLabelRu(state: string): string {
  return EMOTION_MAP[state as EmotionState]?.labelRu ?? state;
}

function getScoreColor(score: number): string {
  return score >= 70 ? "#00FF66" : score >= 40 ? "var(--warning)" : "#FF3333";
}

export default function ResultsPage() {
  const params = useParams();
  const router = useRouter();
  const [result, setResult] = useState<SessionResultResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [repeating, setRepeating] = useState(false);
  const [copied, setCopied] = useState(false);
  const [transcriptCopied, setTranscriptCopied] = useState(false);
  const [achievement, setAchievement] = useState<{ id: string; title: string; description: string; icon?: string } | null>(null);

  // Tournament state
  const [tournament, setTournament] = useState<ActiveTournamentResponse | null>(null);
  const [tournamentSubmitting, setTournamentSubmitting] = useState(false);
  const [tournamentResult, setTournamentResult] = useState<TournamentSubmitResponse | null>(null);
  const [tournamentError, setTournamentError] = useState("");

  useEffect(() => {
    api
      .get(`/training/sessions/${params.id}`)
      .then((data) => {
        setResult(data);
        // Trigger achievement toast based on score
        const score = data?.session?.score_total;
        if (score !== null && score !== undefined) {
          if (score >= 90) {
            setTimeout(() => setAchievement({ id: "ace", title: "Ас переговоров", description: "Набрано 90+ баллов за сессию", icon: "🏆" }), 1500);
          } else if (score >= 70) {
            setTimeout(() => setAchievement({ id: "good", title: "Уверенный старт", description: "Набрано 70+ баллов за сессию", icon: "⭐" }), 1500);
          }
        }
      })
      .catch(console.error)
      .finally(() => setLoading(false));

    // Check active tournament
    api.get("/tournament/active")
      .then((data: ActiveTournamentResponse) => setTournament(data))
      .catch((err) => { console.error("Failed to load active tournament:", err); });
  }, [params.id]);

  const submitToTournament = async () => {
    if (tournamentSubmitting || !session || session.score_total === null) return;
    setTournamentSubmitting(true);
    setTournamentError("");
    try {
      const res: TournamentSubmitResponse = await api.post("/tournament/submit", {
        session_id: session.id,
        score: session.score_total,
      });
      setTournamentResult(res);
    } catch (err: unknown) {
      setTournamentError(err instanceof Error ? err.message : "Ошибка отправки");
    } finally {
      setTournamentSubmitting(false);
    }
  };

  if (loading) {
    return (
      <AuthLayout>
        <div className="flex items-center justify-center min-h-screen">
          <PageSkeleton />
        </div>
      </AuthLayout>
    );
  }

  if (!result) {
    return (
      <div className="flex min-h-screen items-center justify-center" style={{ background: "var(--bg-primary)" }}>
        <div className="flex items-center gap-2" style={{ color: "var(--neon-red)" }}>
          <AlertCircle size={20} />
          Сессия не найдена
        </div>
      </div>
    );
  }

  const { session, messages } = result;
  const story = result.story;
  const totalScore = session.score_total ?? 0;
  const hasScores = session.score_total !== null;
  const totalScoreColor = getScoreColor(totalScore);

  const scoreItems = [
    { label: "Скрипт", value: session.score_script_adherence ?? 0, max: 30 },
    { label: "Возражения", value: session.score_objection_handling ?? 0, max: 25 },
    { label: "Коммуникация", value: session.score_communication ?? 0, max: 20 },
    { label: "Антипаттерны", value: Math.max(0, 15 + (session.score_anti_patterns ?? 0)), max: 15 },
    { label: "Результат", value: session.score_result ?? 0, max: 10 },
  ];

  const pentagramData = {
    labels: scoreItems.map((s) => s.label),
    values: scoreItems.map((s) => (s.max > 0 ? (s.value / s.max) * 100 : 0)),
  };

  const timeline = session.emotion_timeline || [];
  let criticalDrop: { from: string; to: string } | null = null;
  let keyRecovery: { from: string; to: string } | null = null;

  for (let i = 1; i < timeline.length; i++) {
    const prev = stateValues[timeline[i - 1].state] ?? 0;
    const curr = stateValues[timeline[i].state] ?? 0;
    if (curr < prev && !criticalDrop) criticalDrop = { from: timeline[i - 1].state, to: timeline[i].state };
    if (curr > prev && !keyRecovery) keyRecovery = { from: timeline[i - 1].state, to: timeline[i].state };
  }

  return (
    <AuthLayout>
      <AchievementToast achievement={achievement} onClose={() => setAchievement(null)} />

      <div className="max-w-7xl mx-auto w-full p-6 md:p-10 flex flex-col min-h-screen">
        {/* Header */}
        <motion.header
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-10 border-b pb-6 flex flex-col md:flex-row justify-between items-start md:items-end gap-6"
          style={{ borderColor: "var(--border-color)" }}
        >
          <div>
            <div className="font-mono text-sm tracking-[0.3em] mb-2 uppercase" style={{ color: "var(--accent)" }}>
              Flight Log Terminated
            </div>
            <h1 className="font-display font-bold text-4xl md:text-5xl tracking-widest uppercase glow-text-purple" style={{ color: "var(--text-primary)" }}>
              Post-Flight Report
            </h1>
          </div>
          <div className="flex items-end gap-8">
            {hasScores && (
              <div className="text-right">
                <div className="font-mono text-xs tracking-wider mb-1" style={{ color: "var(--text-muted)" }}>OVERALL MASTERY</div>
                <div className="font-display text-5xl font-bold" style={{ color: totalScoreColor, textShadow: `0 0 10px ${totalScoreColor}` }}>
                  {Math.round(totalScore)}<span className="text-2xl" style={{ color: "var(--text-muted)" }}>%</span>
                </div>
              </div>
            )}
            {story && (
              <Link href={`/training/crm/${story.id}`}>
                <motion.span
                  className="flex items-center gap-2 rounded-lg px-4 py-3 font-mono text-xs tracking-widest transition-colors backdrop-blur"
                  style={{ background: "rgba(139,92,246,0.12)", border: "1px solid rgba(139,92,246,0.25)", color: "var(--accent)" }}
                  whileHover={{ background: "rgba(139,92,246,0.2)" }}
                  whileTap={{ scale: 0.97 }}
                >
                  <Layers3 size={14} /> STORY CRM
                </motion.span>
              </Link>
            )}
            <Link href="/training">
              <motion.span
                className="flex items-center gap-2 rounded-lg px-6 py-3 font-mono text-xs tracking-widest transition-colors backdrop-blur"
                style={{ background: "var(--accent-muted)", border: "1px solid var(--accent)", color: "var(--accent)" }}
                whileHover={{ background: "var(--accent)", color: "white" }}
                whileTap={{ scale: 0.97 }}
              >
                <RotateCcw size={14} /> NEW FLIGHT
              </motion.span>
            </Link>
          </div>
        </motion.header>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 flex-1">
          {/* LEFT: Pentagram */}
          {hasScores && (
            <motion.div
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1 }}
              className="col-span-1 lg:col-span-5 glass-panel rounded-2xl p-6 md:p-8 flex flex-col relative overflow-hidden"
            >
              <div className="absolute -top-20 -left-20 w-64 h-64 rounded-full opacity-20 blur-[100px] pointer-events-none" style={{ background: "var(--accent)" }} />

              <h2 className="font-display text-lg tracking-widest flex items-center gap-2 border-b pb-3 z-10 mb-6" style={{ color: "var(--text-primary)", borderColor: "var(--border-color)" }}>
                <Crosshair size={18} style={{ color: "var(--accent)" }} /> THE PENTAGRAM OF MASTERY
              </h2>

              <div className="flex-1 relative z-10">
                <PentagramChart data={pentagramData} />
              </div>

              <div className="mt-4 flex flex-wrap justify-center gap-6 z-10 font-mono text-xs">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 border" style={{ background: "rgba(139,92,246,0.5)", borderColor: "var(--accent)" }} />
                  <span style={{ color: "var(--text-secondary)" }}>YOUR PROFILE</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 border border-dashed" style={{ background: "rgba(255,255,255,0.05)", borderColor: "var(--text-muted)" }} />
                  <span style={{ color: "var(--text-muted)" }}>IDEAL MODEL</span>
                </div>
              </div>
            </motion.div>
          )}

          <div className={`col-span-1 ${hasScores ? "lg:col-span-7" : "lg:col-span-12"} flex flex-col gap-8`}>
            {/* Emotion Timeline */}
            {timeline.length > 0 && (
              <motion.div
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.2 }}
                className="glass-panel rounded-2xl p-6 md:p-8 flex-1 flex flex-col relative overflow-hidden"
              >
                <div className="absolute -bottom-20 -right-20 w-64 h-64 rounded-full opacity-10 blur-[100px] pointer-events-none" style={{ background: "var(--magenta)" }} />

                <h2 className="font-display text-lg tracking-widest flex items-center gap-2 border-b pb-3 z-10 mb-6" style={{ color: "var(--text-primary)", borderColor: "var(--border-color)" }}>
                  <TrendingUp size={18} style={{ color: "var(--magenta)" }} /> TIMELINE EMOTIONS
                </h2>

                <div className="flex-1 w-full relative z-10">
                  <EmotionTimeline timeline={timeline} />
                </div>
              </motion.div>
            )}

            {/* Insight cards */}
            {(criticalDrop || keyRecovery) && (
              <motion.div
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.3 }}
                className="grid grid-cols-1 sm:grid-cols-2 gap-4"
              >
                {criticalDrop && (
                  <div className="glass-panel p-5 rounded-xl" style={{ borderLeft: "4px solid #FF3333", background: "linear-gradient(to right, rgba(255,51,51,0.05), transparent)" }}>
                    <div className="flex items-center gap-2 mb-2">
                      <AlertTriangle size={14} style={{ color: "#FF3333" }} />
                      <div className="font-mono text-[10px] uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>Critical Drop</div>
                    </div>
                    <p className="text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>
                      Эмоция клиента упала: <span style={{ color: "#FF3333" }}>{emotionLabelRu(criticalDrop.from)}</span> → <span style={{ color: "#FF3333" }}>{emotionLabelRu(criticalDrop.to)}</span>
                    </p>
                  </div>
                )}
                {keyRecovery && (
                  <div className="glass-panel p-5 rounded-xl" style={{ borderLeft: "4px solid #00FF66", background: "linear-gradient(to right, rgba(0,255,102,0.05), transparent)" }}>
                    <div className="flex items-center gap-2 mb-2">
                      <CheckCircle size={14} style={{ color: "#00FF66" }} />
                      <div className="font-mono text-[10px] uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>Key Recovery</div>
                    </div>
                    <p className="text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>
                      Восстановление: <span style={{ color: "#00FF66" }}>{emotionLabelRu(keyRecovery.from)}</span> → <span style={{ color: "#00FF66" }}>{emotionLabelRu(keyRecovery.to)}</span>
                    </p>
                  </div>
                )}
              </motion.div>
            )}
          </div>
        </div>

        {story && (
          <motion.div
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.15 }}
            className="glass-panel mt-2 p-6 rounded-2xl"
          >
            <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <Sparkles size={16} style={{ color: "var(--accent)" }} />
                  <span className="font-mono text-[10px] uppercase tracking-widest" style={{ color: "var(--accent)" }}>
                    AI Client Story
                  </span>
                </div>
                <h2 className="mt-2 font-display text-2xl font-bold" style={{ color: "var(--text-primary)" }}>
                  {story.story_name}
                </h2>
                <p className="mt-2 text-sm" style={{ color: "var(--text-secondary)" }}>
                  Звонок {session.call_number_in_story ?? story.current_call_number} из {story.total_calls_planned}. Эта сессия входит в одну общую историю клиента, а не является изолированным разговором.
                </p>
              </div>
              <div className="grid grid-cols-2 gap-3 md:min-w-[320px]">
                {[
                  { label: "Средний балл story", value: story.avg_score !== null ? Math.round(story.avg_score) : "—" },
                  { label: "Статус клиента", value: story.game_status },
                  { label: "Факторы", value: story.active_factors.length },
                  { label: "Последствия", value: story.consequences.length },
                ].map((item) => (
                  <div key={item.label} className="rounded-xl p-3" style={{ background: "var(--input-bg)" }}>
                    <div className="font-mono text-[10px] uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
                      {item.label}
                    </div>
                    <div className="mt-1 text-lg font-semibold" style={{ color: "var(--text-primary)" }}>
                      {item.value}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {result.story_calls.length > 0 && (
              <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                {result.story_calls.map((call) => (
                  <div key={call.session_id} className="rounded-xl p-4" style={{ background: "rgba(255,255,255,0.03)", border: "1px solid var(--border-color)" }}>
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-[10px] uppercase tracking-widest" style={{ color: "var(--accent)" }}>
                        Call {call.call_number}
                      </span>
                      <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                        {call.status}
                      </span>
                    </div>
                      <div className="mt-3 text-2xl font-bold" style={{ color: call.score_total !== null ? getScoreColor(call.score_total) : "var(--text-muted)" }}>
                      {call.score_total !== null ? Math.round(call.score_total) : "—"}
                    </div>
                    <div className="mt-2 text-xs" style={{ color: "var(--text-muted)" }}>
                      {formatDuration(call.duration_seconds)}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </motion.div>
        )}

        {/* Trap Results */}
        {result.trap_results && result.trap_results.length > 0 && (
          <div className="mt-8">
            <TrapResults traps={result.trap_results} />
          </div>
        )}

        {/* Soft Skills */}
        {result.soft_skills && (
          <div className="mt-6">
            <SoftSkillsCard skills={result.soft_skills} />
          </div>
        )}

        {/* Score bars */}
        {hasScores && (
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.4 }}
            className="glass-panel mt-8 p-6 rounded-2xl"
          >
            <div className="space-y-3">
              {scoreItems.map((item, i) => {
                const pct = item.max > 0 ? (item.value / item.max) * 100 : 0;
                const barColor = pct >= 70 ? "#00FF66" : pct >= 40 ? "var(--warning)" : "#FF3333";
                return (
                  <motion.div key={item.label} initial={{ opacity: 0, x: -16 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.5 + i * 0.1 }}>
                    <div className="flex items-center justify-between text-sm">
                      <span className="font-medium" style={{ color: "var(--text-primary)" }}>{item.label}</span>
                      <span className="font-mono text-xs" style={{ color: "var(--text-muted)" }}>{Math.round(item.value)} / {item.max}</span>
                    </div>
                    <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full" style={{ background: "var(--input-bg)" }}>
                      <motion.div
                        className="h-full rounded-full"
                        initial={{ width: 0 }}
                        animate={{ width: `${Math.min(pct, 100)}%` }}
                        transition={{ duration: 0.8, delay: 0.6 + i * 0.1 }}
                        style={{ background: barColor, boxShadow: `0 0 5px ${barColor}` }}
                      />
                    </div>
                  </motion.div>
                );
              })}
            </div>
          </motion.div>
        )}

        {/* Checkpoint Progress */}
        {result.score_breakdown?.script_adherence?.checkpoints && (
          <div className="mt-6">
            <CheckpointProgress checkpoints={result.score_breakdown.script_adherence.checkpoints} />
          </div>
        )}

        {/* AI Recommendations (markdown) — fallback if LLM didn't generate feedback */}
        <div className="mt-6">
          <AIRecommendations
            text={
              session.feedback_text ||
              "Анализ сессии завершён. Детальные рекомендации от AI будут доступны после обработки — обычно это занимает несколько минут. Попробуйте обновить страницу позже."
            }
          />
        </div>

        {/* Tournament Submit Banner */}
        {tournament?.tournament && tournament.tournament.scenario_id === session.scenario_id && hasScores && (
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.55 }}
            className="glass-panel mt-8 p-6 rounded-2xl relative overflow-hidden"
            style={{ borderColor: "rgba(255,215,0,0.3)" }}
          >
            <div className="absolute top-0 left-0 right-0 h-[2px]" style={{ background: "linear-gradient(90deg, transparent, #FFD700, transparent)" }} />
            <div className="absolute -top-10 -right-10 w-40 h-40 rounded-full opacity-10 blur-[60px] pointer-events-none" style={{ background: "#FFD700" }} />

            <div className="flex items-start gap-4 relative z-10">
              <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl" style={{ background: "rgba(255,215,0,0.1)", border: "1px solid rgba(255,215,0,0.2)" }}>
                <Trophy size={22} style={{ color: "#FFD700" }} />
              </div>

              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <Swords size={14} style={{ color: "#FFD700" }} />
                  <span className="font-mono text-[10px] uppercase tracking-widest" style={{ color: "#FFD700" }}>ЕЖЕНЕДЕЛЬНЫЙ ТУРНИР</span>
                </div>
                <h3 className="font-display text-lg font-bold" style={{ color: "var(--text-primary)" }}>
                  {tournament.tournament.title}
                </h3>
                <p className="text-sm mt-1" style={{ color: "var(--text-secondary)" }}>
                  Отправьте результат этой сессии в турнир и соревнуйтесь за призовые XP!
                </p>

                {/* Prize info */}
                <div className="mt-3 flex items-center gap-4 font-mono text-xs">
                  <span className="flex items-center gap-1" style={{ color: "#FFD700" }}>
                    <Crown size={12} /> {tournament.tournament.bonus_xp[0]} XP
                  </span>
                  <span className="flex items-center gap-1" style={{ color: "#C0C0C0" }}>
                    <Medal size={12} /> {tournament.tournament.bonus_xp[1]} XP
                  </span>
                  <span className="flex items-center gap-1" style={{ color: "#CD7F32" }}>
                    <Medal size={12} /> {tournament.tournament.bonus_xp[2]} XP
                  </span>
                </div>

                {/* Leaderboard mini (top 3) */}
                {tournament.leaderboard.length > 0 && (
                  <div className="mt-3 flex items-center gap-3">
                    {tournament.leaderboard.slice(0, 3).map((e) => (
                      <span key={e.user_id} className="font-mono text-[10px] flex items-center gap-1 px-2 py-1 rounded-full"
                        style={{ background: "var(--input-bg)", color: "var(--text-muted)" }}
                      >
                        {e.rank === 1 ? "🥇" : e.rank === 2 ? "🥈" : "🥉"} {e.full_name.split(" ")[0]} · {Math.round(e.best_score)}
                      </span>
                    ))}
                    {tournament.leaderboard.length > 3 && (
                      <span className="font-mono text-[10px]" style={{ color: "var(--text-muted)" }}>
                        +{tournament.leaderboard.length - 3}
                      </span>
                    )}
                  </div>
                )}

                {/* Submit result */}
                {tournamentResult ? (
                  <motion.div
                    initial={{ opacity: 0, y: 4 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="mt-4 flex items-center gap-2 rounded-xl p-3 text-sm"
                    style={{ background: "rgba(0,255,102,0.08)", border: "1px solid rgba(0,255,102,0.2)", color: "var(--neon-green, #00FF66)" }}
                  >
                    <CheckCircle size={16} />
                    Результат отправлен! Попытка {tournamentResult.attempt} · {Math.round(tournamentResult.score)} баллов
                  </motion.div>
                ) : (
                  <div className="mt-4 flex items-center gap-3">
                    <motion.button
                      onClick={submitToTournament}
                      disabled={tournamentSubmitting}
                      className="vh-btn-primary flex items-center gap-2"
                      whileTap={{ scale: 0.97 }}
                    >
                      {tournamentSubmitting ? (
                        <Loader2 size={16} className="animate-spin" />
                      ) : (
                        <>
                          <Trophy size={16} /> Отправить в турнир ({Math.round(totalScore)} баллов)
                        </>
                      )}
                    </motion.button>
                    <span className="font-mono text-[10px]" style={{ color: "var(--text-muted)" }}>
                      макс. {tournament.tournament.max_attempts} попыток
                    </span>
                  </div>
                )}

                {tournamentError && (
                  <div className="mt-2 flex items-center gap-2 text-xs" style={{ color: "var(--neon-red, #FF3333)" }}>
                    <AlertCircle size={14} />
                    {tournamentError}
                  </div>
                )}
              </div>
            </div>
          </motion.div>
        )}

        {/* Client Reveal — hidden data revealed post-session */}
        {result.client_card && (
          <div className="mt-6">
            <ClientReveal clientCard={result.client_card} />
          </div>
        )}

        {/* Transcript */}
        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.7 }} className="glass-panel mt-6 p-6 rounded-2xl">
          <div className="mb-3 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <MessageSquare size={14} style={{ color: "var(--text-muted)" }} />
              <p className="font-mono text-[10px] uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
                TRANSCRIPT ({messages.length} MESSAGES)
              </p>
            </div>
            <div className="flex items-center gap-2">
              <motion.button
                onClick={async () => {
                  const meta = {
                    sessionId: session.id,
                    scenarioTitle: undefined,
                    date: session.started_at ? new Date(session.started_at).toLocaleDateString("ru-RU") : new Date().toLocaleDateString("ru-RU"),
                    score: session.score_total,
                    emotion: timeline.length > 0 ? emotionLabelRu(timeline[timeline.length - 1].state) : undefined,
                    duration: session.duration_seconds ? formatDuration(session.duration_seconds) : undefined,
                  };
                  const msgs = messages.map((m) => ({
                    role: m.role as "user" | "assistant" | "system",
                    text: m.content,
                    timestamp: m.created_at ? new Date(m.created_at).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" }) : undefined,
                  }));
                  const ok = await copyTranscript(meta, msgs);
                  if (ok) {
                    setTranscriptCopied(true);
                    setTimeout(() => setTranscriptCopied(false), 2000);
                  }
                }}
                className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 font-mono text-[10px] uppercase tracking-widest transition-colors"
                style={{ background: "var(--input-bg)", color: transcriptCopied ? "var(--neon-green, #00FF66)" : "var(--text-muted)", border: "1px solid var(--border-color)" }}
                whileTap={{ scale: 0.95 }}
                title="Скопировать транскрипт"
              >
                {transcriptCopied ? <ClipboardCheck size={12} /> : <Copy size={12} />}
                {transcriptCopied ? "Скопировано" : "Копировать"}
              </motion.button>
              <motion.button
                onClick={() => {
                  const meta = {
                    sessionId: session.id,
                    scenarioTitle: undefined,
                    date: session.started_at ? new Date(session.started_at).toLocaleDateString("ru-RU") : new Date().toLocaleDateString("ru-RU"),
                    score: session.score_total,
                    emotion: timeline.length > 0 ? emotionLabelRu(timeline[timeline.length - 1].state) : undefined,
                    duration: session.duration_seconds ? formatDuration(session.duration_seconds) : undefined,
                  };
                  const msgs = messages.map((m) => ({
                    role: m.role as "user" | "assistant" | "system",
                    text: m.content,
                    timestamp: m.created_at ? new Date(m.created_at).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" }) : undefined,
                  }));
                  downloadTranscript(meta, msgs);
                }}
                className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 font-mono text-[10px] uppercase tracking-widest transition-colors"
                style={{ background: "var(--input-bg)", color: "var(--text-muted)", border: "1px solid var(--border-color)" }}
                whileTap={{ scale: 0.95 }}
                title="Скачать транскрипт (.md)"
              >
                <Download size={12} />
                Скачать
              </motion.button>
            </div>
          </div>
          <div className="max-h-[500px] space-y-2 overflow-y-auto">
            {messages.map((msg) => (
              <div key={msg.id} className="flex gap-3 rounded-lg p-2" style={{ background: msg.role !== "user" ? "var(--input-bg)" : "transparent" }}>
                <span
                  className="w-16 shrink-0 font-mono text-[10px] uppercase"
                  style={{ color: msg.role === "user" ? "var(--accent)" : emotionColor(msg.emotion_state || "") }}
                >
                  {msg.role === "user" ? "YOU" : "CLIENT"}
                </span>
                <div className="flex-1">
                  <p className="text-sm" style={{ color: "var(--text-secondary)" }}>{msg.content}</p>
                  {msg.emotion_state && (
                    <span className="mt-1 inline-block rounded-full px-2 py-0.5 text-[10px]"
                      style={{ background: "var(--accent-muted)", color: emotionColor(msg.emotion_state) }}
                    >
                      {emotionLabelRu(msg.emotion_state)}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </motion.div>

        {/* Actions */}
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.8 }} className="mt-8 flex justify-center gap-3 pb-8">
          <motion.button
            onClick={() => {
              navigator.clipboard.writeText(window.location.href);
              setCopied(true);
              setTimeout(() => setCopied(false), 2000);
            }}
            className="vh-btn-outline flex items-center gap-2"
            whileTap={{ scale: 0.97 }}
          >
            {copied ? <Check size={16} /> : <Share2 size={16} />}
            {copied ? "Скопировано" : "Поделиться"}
          </motion.button>
          <Link href="/">
            <motion.span className="vh-btn-outline flex items-center gap-2" whileTap={{ scale: 0.97 }}>
              <Home size={16} /> На главную
            </motion.span>
          </Link>
          <motion.button
            onClick={async () => {
              if (repeating || !session.scenario_id) return;
              setRepeating(true);
              try {
                const newSession = await api.post("/training/sessions", { scenario_id: session.scenario_id });
                router.push(`/training/${newSession.id}`);
              } catch {
                setRepeating(false);
              }
            }}
            disabled={repeating}
            className="vh-btn-outline flex items-center gap-2"
            whileTap={{ scale: 0.97 }}
          >
            {repeating ? <Loader2 size={16} className="animate-spin" /> : <Repeat size={16} />}
            Повторить сценарий
          </motion.button>
          <Link href="/training">
            <motion.span className="vh-btn-primary flex items-center gap-2" whileTap={{ scale: 0.97 }}>
              Новая тренировка <ArrowRight size={16} />
            </motion.span>
          </Link>
        </motion.div>
      </div>
    </AuthLayout>
  );
}
