"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { motion } from "framer-motion";
import {
  Clock,
  ArrowRight,
  Home,
  Users,
  Zap,
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
    BookOpen,
    Handshake,
  } from "lucide-react";
import { api } from "@/lib/api";
import { downloadTranscript, copyTranscript, copyToClipboard } from "@/lib/exportTranscript";
import AuthLayout from "@/components/layout/AuthLayout";
import { PageSkeleton } from "@/components/ui/Skeleton";
import dynamic from "next/dynamic";
import { Skeleton } from "@/components/ui/Skeleton";

const PentagramChart = dynamic(() => import("@/components/results/PentagramChart"), {
  loading: () => <Skeleton height={280} width="100%" rounded="12px" />, ssr: false,
});
const EmotionTimeline = dynamic(() => import("@/components/results/EmotionTimeline"), {
  loading: () => <Skeleton height={200} width="100%" rounded="12px" />, ssr: false,
});
import TrapResults from "@/components/results/TrapResults";
import SoftSkillsCard from "@/components/results/SoftSkillsCard";
import ClientReveal from "@/components/results/ClientReveal";
import AIRecommendations from "@/components/results/AIRecommendations";
import CheckpointProgress from "@/components/results/CheckpointProgress";
import StageBreakdown from "@/components/results/StageBreakdown";
import ScriptProgressReport from "@/components/results/ScriptProgressReport";
import AICoachSection from "@/components/results/AICoachSection";
import ScoreLayersBreakdown from "@/components/results/ScoreLayersBreakdown";
import JudgeVerdictCard from "@/components/results/JudgeVerdictCard";
import MistakesBreakdown from "@/components/results/MistakesBreakdown";
import ReplayModal from "@/components/results/ReplayModal";
import { AchievementToast } from "@/components/gamification/AchievementToast";
import { PostSessionVerdict } from "@/components/results/PostSessionVerdict";
import { BackButton } from "@/components/ui/BackButton";
import { Button } from "@/components/ui/Button";
import { Breadcrumb } from "@/components/ui/Breadcrumb";
import { EMOTION_MAP, type EmotionState, type ChatMessage, type SessionResultResponse, type ActiveTournamentResponse, type TournamentSubmitResponse } from "@/types";
import { logger } from "@/lib/logger";
import { colorAlpha } from "@/lib/utils";

function formatDuration(seconds: number | null): string {
  if (seconds === null || seconds === undefined) return "--:--";
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
  return score >= 70 ? "var(--success)" : score >= 40 ? "var(--gf-xp)" : "var(--danger)";
}

export default function ResultsPage() {
  const params = useParams();
  const router = useRouter();
  const [result, setResult] = useState<SessionResultResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [repeating, setRepeating] = useState(false);
  const [showVerdict, setShowVerdict] = useState(true);
  const [copied, setCopied] = useState(false);
  const [transcriptCopied, setTranscriptCopied] = useState(false);
  const [achievement, setAchievement] = useState<{ id: string; title: string; description: string; icon?: string } | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [addedToCRM, setAddedToCRM] = useState(false);

  // Replay Mode state
  const [replayMessage, setReplayMessage] = useState<{ msg: ChatMessage; index: number } | null>(null);

  // Tournament state
  const [tournament, setTournament] = useState<ActiveTournamentResponse | null>(null);
  const [tournamentSubmitting, setTournamentSubmitting] = useState(false);
  const [tournamentResult, setTournamentResult] = useState<TournamentSubmitResponse | null>(null);
  const [tournamentError, setTournamentError] = useState("");
  const [previousSkillRadar, setPreviousSkillRadar] = useState<Record<string, number> | null>(null);

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
            // Emit perfect-score celebration
            setTimeout(() => {
              window.dispatchEvent(new CustomEvent("gamification", { detail: { type: "perfect-score", score } }));
            }, 800);
          } else if (score >= 70) {
            setTimeout(() => setAchievement({ id: "good", title: "Уверенный старт", description: "Набрано 70+ баллов за сессию", icon: "⭐" }), 1500);
          }
        }

        // Fetch previous session for skill radar comparison
        api.get<Array<{ id: string; scoring_details?: Record<string, unknown> }>>("/training/history?limit=5")
          .then((history) => {
            const currentId = String(params.id);
            const prev = history.find((h) => h.id !== currentId && h.scoring_details?._skill_radar);
            if (prev) {
              setPreviousSkillRadar(prev.scoring_details?._skill_radar as Record<string, number>);
            }
          })
          .catch(() => { /* optional: previous radar not critical */ });
      })
      .catch((err) => {
        logger.error("Failed to load results:", err);
        setLoadError(err instanceof Error ? err.message : "Не удалось загрузить результаты сессии");
      })
      .finally(() => setLoading(false));

    // Check active tournament
    api.get("/tournament/active")
      .then((data: ActiveTournamentResponse) => setTournament(data))
      .catch((err) => { logger.error("Failed to load active tournament:", err); });
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

  if (loadError) {
    return (
      <AuthLayout>
        <div className="flex min-h-screen items-center justify-center" style={{ background: "var(--bg-primary)" }}>
          <div className="text-center" style={{ maxWidth: 400 }}>
            <AlertCircle size={48} style={{ color: "var(--danger)", margin: "0 auto 16px" }} />
            <h2 style={{ color: "var(--text-primary)", marginBottom: 8 }}>Ошибка загрузки</h2>
            <p style={{ color: "var(--text-muted)", marginBottom: 24 }}>{loadError}</p>
            <button
              onClick={() => { setLoadError(null); setLoading(true); window.location.reload(); }}
              className="px-4 py-2 rounded"
              style={{ background: "var(--accent)", color: "#000" }}
            >
              Попробовать снова
            </button>
          </div>
        </div>
      </AuthLayout>
    );
  }

  if (!result) {
    return (
      <div className="flex min-h-screen items-center justify-center" style={{ background: "var(--bg-primary)" }}>
        <div className="flex items-center gap-2" style={{ color: "var(--danger)" }}>
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
  const completeness = (result.score_breakdown as unknown as Record<string, number>)?._completeness ?? 1;
  const userMsgCount = (result.score_breakdown as unknown as Record<string, number>)?._user_message_count ?? 0;

  // Layer-based score bars (original 5 categories)
  const scoreItems = [
    { label: "Скрипт", value: session.score_script_adherence ?? 0, max: 30 },
    { label: "Возражения", value: session.score_objection_handling ?? 0, max: 25 },
    { label: "Коммуникация", value: session.score_communication ?? 0, max: 20 },
    { label: "Антипаттерны", value: Math.max(0, 15 + (session.score_anti_patterns ?? 0)), max: 15 },
    { label: "Результат", value: session.score_result ?? 0, max: 10 },
  ];

  // 6-axis Skill Radar from backend (computed from all 10 scoring layers)
  const skillRadar = (result.score_breakdown as Record<string, unknown> | null)?._skill_radar as
    Record<string, number> | undefined;

  const pentagramData = skillRadar
    ? {
        labels: ["Эмпатия", "Знания", "Возражения", "Стрессоуст.", "Закрытие", "Квалификация", "Тайм-менедж.", "Адаптация", "Юрид. знания", "Раппорт"],
        values: [
          Math.min(100, Math.max(0, skillRadar.empathy ?? 0)),
          Math.min(100, Math.max(0, skillRadar.knowledge ?? 0)),
          Math.min(100, Math.max(0, skillRadar.objection_handling ?? 0)),
          Math.min(100, Math.max(0, skillRadar.stress_resistance ?? 0)),
          Math.min(100, Math.max(0, skillRadar.closing ?? 0)),
          Math.min(100, Math.max(0, skillRadar.qualification ?? 0)),
          Math.min(100, Math.max(0, skillRadar.time_management ?? 0)),
          Math.min(100, Math.max(0, (skillRadar.adaptation ?? skillRadar.adaptability ?? 0))),
          Math.min(100, Math.max(0, skillRadar.legal_knowledge ?? 0)),
          Math.min(100, Math.max(0, (skillRadar.rapport_building ?? skillRadar.rapport ?? 0))),
        ],
        // Previous session overlay for progress comparison
        previousValues: previousSkillRadar
          ? [
              Math.min(100, Math.max(0, previousSkillRadar.empathy ?? 0)),
              Math.min(100, Math.max(0, previousSkillRadar.knowledge ?? 0)),
              Math.min(100, Math.max(0, previousSkillRadar.objection_handling ?? 0)),
              Math.min(100, Math.max(0, previousSkillRadar.stress_resistance ?? 0)),
              Math.min(100, Math.max(0, previousSkillRadar.closing ?? 0)),
              Math.min(100, Math.max(0, previousSkillRadar.qualification ?? 0)),
              Math.min(100, Math.max(0, previousSkillRadar.time_management ?? 0)),
              Math.min(100, Math.max(0, (previousSkillRadar.adaptation ?? previousSkillRadar.adaptability ?? 0))),
              Math.min(100, Math.max(0, previousSkillRadar.legal_knowledge ?? 0)),
              Math.min(100, Math.max(0, (previousSkillRadar.rapport_building ?? previousSkillRadar.rapport ?? 0))),
            ]
          : undefined,
      }
    : {
        // Fallback to 5-axis if skill_radar not available
        labels: scoreItems.map((s) => s.label),
        values: scoreItems.map((s) => (s.max > 0 ? (s.value / s.max) * 100 : 0)),
      };

  // Stage progress data (from stage tracker)
  const stageProgress = (result.score_breakdown as Record<string, unknown> | null)?._stage_progress as
    {
      stages_completed?: number[];
      stage_scores?: Record<string, number>;
      skipped_stages?: number[];
      stage_durations_sec?: Record<string, number>;
      stage_message_counts?: Record<string, number>;
      final_stage?: number;
      total_stages?: number;
      call_outcome?: string;
    } | undefined;

  const timeline = session.emotion_timeline || [];
  const emotionJourney = (result.score_breakdown as Record<string, unknown> | null)?._emotion_journey as
    {
      summary?: {
        total_transitions?: number;
        rollback_count?: number;
        peak_state?: string;
        fake_count?: number;
        turning_points?: Array<{
          message_index?: number | null;
          from_state: string;
          to_state: string;
          direction: string;
          triggers?: string[];
        }>;
      };
      timeline?: unknown[];
    } | undefined;
  const journeySummary = emotionJourney?.summary;
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

      {/* Score verdict overlay — shows first, then fades into full report */}
      {showVerdict && hasScores && (
        <PostSessionVerdict
          score={totalScore}
          xpGained={result.xp_breakdown?.grand_total ?? result.xp_breakdown?.session_total ?? 0}
          onContinue={() => setShowVerdict(false)}
        />
      )}

      <div className="app-page flex flex-col min-h-screen" style={{ display: showVerdict && hasScores ? "none" : undefined }}>
        <Breadcrumb items={[{ label: "История", href: "/history" }, { label: "Результат" }]} />
        <BackButton href="/training" label="К тренировкам" />

        {/* Completeness warning for short conversations */}
        {completeness < 0.6 && (
          <div
            className="mt-3 mb-4 flex items-center gap-3 rounded-2xl border px-4 py-3 text-sm"
            style={{
              borderColor: "rgba(255,180,0,0.3)",
              background: "rgba(255,180,0,0.06)",
              color: "var(--warning)",
            }}
          >
            <AlertTriangle size={16} />
            Разговор был коротким ({userMsgCount} сообщ.). Баллы снижены пропорционально. Для полной оценки проведите сессию с 10+ репликами.
          </div>
        )}

        {/* Header */}
        <motion.header
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-10 border-b pb-6 flex flex-col md:flex-row justify-between items-start md:items-end gap-6"
          style={{ borderColor: "var(--border-color)" }}
        >
          <div>
            <div className="font-mono text-sm tracking-widest mb-2 uppercase" style={{ color: "var(--accent)" }}>
              Сессия завершена
            </div>
            <h1 className="font-display font-bold text-3xl md:text-4xl tracking-wide uppercase " style={{ color: "var(--text-primary)" }}>
              Отчёт по сессии
            </h1>
          </div>
          <div className="flex items-end gap-8">
            {hasScores && (
              <div className="text-right flex flex-col items-center">
                <div className="font-mono text-sm tracking-wider mb-2" style={{ color: "var(--text-muted)" }}>ОБЩИЙ БАЛЛ</div>
                <div className="score-ring relative" style={{ "--ring-color": totalScoreColor } as React.CSSProperties}>
                  <svg width="96" height="96" viewBox="0 0 96 96">
                    <circle cx="48" cy="48" r="42" fill="none" stroke="var(--border-color)" strokeWidth="4" opacity="0.3" />
                    <circle
                      cx="48" cy="48" r="42" fill="none"
                      stroke={totalScoreColor}
                      strokeWidth="4"
                      strokeLinecap="round"
                      strokeDasharray={`${2 * Math.PI * 42 * (totalScore / 100)} ${2 * Math.PI * 42}`}
                      transform="rotate(-90 48 48)"
                      style={{ filter: `drop-shadow(0 0 6px ${totalScoreColor})`, transition: "stroke-dasharray 1s ease-out" }}
                    />
                  </svg>
                  <div className="absolute inset-0 flex items-center justify-center">
                    <span className="font-display text-3xl font-bold" style={{ color: totalScoreColor, textShadow: `0 0 10px ${totalScoreColor}` }}>
                      {Math.round(totalScore)}
                    </span>
                  </div>
                </div>
              </div>
            )}
            {story && (
              <Link href={`/stories/${story.id}`}>
                <motion.span
                  className="flex items-center gap-2 rounded-lg px-4 py-3 font-mono text-xs tracking-widest transition-colors backdrop-blur"
                  style={{ background: "var(--accent-muted)", border: "1px solid var(--accent-glow)", color: "var(--accent)" }}
                  whileHover={{ background: "var(--accent-glow)" }}
                  whileTap={{ scale: 0.97 }}
                >
                  <Layers3 size={14} /> ИСТОРИЯ CRM
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
                <RotateCcw size={14} /> НОВАЯ ТРЕНИРОВКА
              </motion.span>
            </Link>
          </div>
        </motion.header>

        {/* B3 v3: AI-judge verdict + per-mistake breakdown */}
        {result.score_breakdown?.judge && (
          <div className="mb-6">
            <JudgeVerdictCard judge={result.score_breakdown.judge} />
          </div>
        )}
        <div className="mb-8">
          <MistakesBreakdown items={result.score_breakdown?.anti_patterns?.detected ?? []} />
        </div>

        {/* XP Rewards banner */}
        {result.xp_breakdown && (
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 0.15 }}
            className="mb-8 glass-panel rounded-2xl p-5 flex flex-wrap items-center justify-between gap-4"
          >
            <div className="flex items-center gap-6">
              <div className="flex items-center gap-2">
                <Zap size={20} style={{ color: "var(--warning)" }} />
                <span className="font-display font-bold text-xl" style={{ color: "var(--warning)" }}>
                  +{result.xp_breakdown.grand_total ?? result.xp_breakdown.session_total ?? 0} XP
                </span>
              </div>
              {result.level_up && (
                <div className="flex items-center gap-2 rounded-xl px-3 py-1.5" style={{ background: "rgba(61,220,132,0.1)", border: "1px solid rgba(61,220,132,0.3)" }}>
                  <Trophy size={16} style={{ color: "var(--success)" }} />
                  <span className="font-display font-bold text-sm" style={{ color: "var(--success)" }}>
                    Уровень {result.new_level}!
                  </span>
                </div>
              )}
            </div>
            <div className="flex items-center gap-4 text-sm font-mono" style={{ color: "var(--text-muted)" }}>
              {result.xp_breakdown.base && <span>База: +{result.xp_breakdown.base}</span>}
              {result.xp_breakdown.score_bonus > 0 && <span>За баллы: +{result.xp_breakdown.score_bonus}</span>}
              {result.xp_breakdown.streak_bonus > 0 && <span>Стрик: +{result.xp_breakdown.streak_bonus}</span>}
              {result.xp_breakdown.achievements > 0 && <span>Ачивки: +{result.xp_breakdown.achievements}</span>}
            </div>
          </motion.div>
        )}

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
                <Crosshair size={18} style={{ color: "var(--accent)" }} /> {skillRadar ? "РАДАР НАВЫКОВ" : "ПЕНТАГРАММА НАВЫКОВ"}
              </h2>

              <div className="flex-1 relative z-10">
                <PentagramChart data={pentagramData} />
              </div>

              <div className="mt-4 flex flex-wrap justify-center gap-6 z-10 font-mono text-sm">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 border" style={{ background: "var(--accent-glow)", borderColor: "var(--accent)" }} />
                  <span style={{ color: "var(--text-secondary)" }}>Ваш профиль</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 border border-dashed" style={{ background: "rgba(255,255,255,0.05)", borderColor: "var(--text-muted)" }} />
                  <span style={{ color: "var(--text-muted)" }}>Идеальная модель</span>
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
                  <TrendingUp size={18} style={{ color: "var(--magenta)" }} /> ЭМОЦИИ ПО ВРЕМЕНИ
                </h2>

                <div className="flex-1 w-full relative z-10">
                  <EmotionTimeline
                    timeline={timeline}
                    journeySummary={journeySummary}
                    onReplayMessage={(msgIdx) => {
                      // Find the nearest user message at or after this index for Replay Mode
                      const msg = messages.find((m, i) => i >= msgIdx && m.role === "user");
                      if (msg) {
                        setReplayMessage({ msg, index: messages.indexOf(msg) });
                      }
                    }}
                  />
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
                  <div className="glass-panel p-5 rounded-xl" style={{ borderLeft: "4px solid var(--danger)", background: "linear-gradient(to right, var(--danger-muted), transparent)" }}>
                    <div className="flex items-center gap-2 mb-2">
                      <AlertTriangle size={14} style={{ color: "var(--danger)" }} />
                      <div className="font-mono text-sm uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>Критич. падение</div>
                    </div>
                    <p className="text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>
                      Эмоция клиента упала: <span style={{ color: "var(--danger)" }}>{emotionLabelRu(criticalDrop.from)}</span> → <span style={{ color: "var(--danger)" }}>{emotionLabelRu(criticalDrop.to)}</span>
                    </p>
                  </div>
                )}
                {keyRecovery && (
                  <div className="glass-panel p-5 rounded-xl" style={{ borderLeft: "4px solid var(--success)", background: "linear-gradient(to right, rgba(61,220,132,0.05), transparent)" }}>
                    <div className="flex items-center gap-2 mb-2">
                      <CheckCircle size={14} style={{ color: "var(--success)" }} />
                      <div className="font-mono text-sm uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>Восстановление</div>
                    </div>
                    <p className="text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>
                      Восстановление: <span style={{ color: "var(--success)" }}>{emotionLabelRu(keyRecovery.from)}</span> → <span style={{ color: "var(--success)" }}>{emotionLabelRu(keyRecovery.to)}</span>
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
                  <span className="font-mono text-sm uppercase tracking-widest" style={{ color: "var(--accent)" }}>
                    История клиента
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
                    <div className="font-mono text-xs uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
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
                      <span className="font-mono text-xs uppercase tracking-widest" style={{ color: "var(--accent)" }}>
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

        {/* L1-L10 Detailed Score Layers */}
        {hasScores && (
          <div className="mt-6">
            <ScoreLayersBreakdown
              scoreBreakdown={{
                score_script_adherence: session.score_script_adherence ?? 0,
                score_objection_handling: session.score_objection_handling ?? 0,
                score_communication: session.score_communication ?? 0,
                score_anti_patterns: session.score_anti_patterns ?? 0,
                score_result: session.score_result ?? 0,
                score_chain_traversal: session.score_chain_traversal ?? 0,
                score_trap_handling: session.score_trap_handling ?? 0,
                score_human_factor: session.score_human_factor ?? 0,
                score_narrative: session.score_narrative ?? 0,
                score_legal: session.score_legal ?? 0,
              }}
              totalScore={totalScore}
              layerExplanations={session.scoring_details?._layer_explanations as import("@/components/results/ScoreLayersBreakdown").LayerExplanation[] | undefined}
            />
          </div>
        )}

        {/* 3.1: Weak legal areas → Knowledge Quiz link */}
        {result.weak_legal_categories && result.weak_legal_categories.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.35 }}
            className="cyber-card mt-6 p-5 relative overflow-hidden"
          >
            <div className="absolute top-0 left-0 right-0 h-[2px]" style={{ background: "linear-gradient(90deg, transparent, var(--danger), transparent)" }} />
            <div className="flex items-start gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl" style={{ background: "var(--danger-muted)", border: "1px solid var(--danger-muted)" }}>
                <BookOpen size={18} style={{ color: "var(--danger)" }} />
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <AlertTriangle size={12} style={{ color: "var(--danger)" }} />
                  <span className="font-mono text-xs uppercase tracking-widest" style={{ color: "var(--danger)" }}>СЛАБЫЕ МЕСТА ПО ФЗ-127</span>
                </div>
                <p className="text-sm mb-3" style={{ color: "var(--text-secondary)" }}>
                  Ваша юридическая точность ниже нормы. Подтяните знания в этих категориях:
                </p>
                <div className="flex flex-wrap gap-2 mb-4">
                  {result.weak_legal_categories.map((cat: { category: string; display_name: string; accuracy_pct: number }) => (
                    <Link key={cat.category} href={`/pvp?tab=knowledge&category=${encodeURIComponent(cat.category)}`}>
                      <span className="status-badge status-badge--danger" style={{ cursor: "pointer" }}>
                        {cat.display_name} · {cat.accuracy_pct}%
                      </span>
                    </Link>
                  ))}
                </div>
                <Button href={`/pvp?tab=knowledge&category=${encodeURIComponent(result.weak_legal_categories[0]?.category || "")}`} size="sm" icon={<BookOpen size={14} />}>
                    Подтяни знания по ФЗ-127
                </Button>
              </div>
            </div>
          </motion.div>
        )}

        {/* 3.2: Promise fulfillment from CRM story */}
        {result.promise_fulfillment && result.promise_fulfillment.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.38 }}
            className="glass-panel mt-6 p-5"
          >
            <div className="flex items-center gap-2 mb-3">
              <Handshake size={14} style={{ color: "var(--accent)" }} />
              <span className="font-mono text-xs uppercase tracking-widest" style={{ color: "var(--accent)" }}>ВЫПОЛНЕНИЕ ОБЕЩАНИЙ</span>
            </div>
            <div className="space-y-2">
              {result.promise_fulfillment.map((p: { text: string; call_number: number; fulfilled: boolean; impact: string }, i: number) => (
                <div
                  key={i}
                  className="flex items-center gap-3 rounded-lg p-2.5"
                  style={{
                    background: p.fulfilled ? "var(--success-muted)" : "var(--danger-muted)",
                    border: `1px solid ${p.fulfilled ? "var(--success-muted)" : "var(--danger-muted)"}`,
                  }}
                >
                  {p.fulfilled ? (
                    <CheckCircle size={14} style={{ color: "var(--success)" }} />
                  ) : (
                    <AlertCircle size={14} style={{ color: "var(--danger)" }} />
                  )}
                  <div className="flex-1">
                    <span className="text-xs" style={{ color: "var(--text-primary)" }}>{p.text}</span>
                    <span className="ml-2 font-mono text-xs" style={{ color: "var(--text-muted)" }}>
                      Звонок #{p.call_number}
                    </span>
                  </div>
                  <span className={`stat-chip ${p.fulfilled ? "" : "neon-pulse"}`} style={{
                    color: p.fulfilled ? "var(--success)" : "var(--danger)",
                    fontSize: "14px",
                  }}>
                    {p.fulfilled ? "+0.5" : "−1.0"}
                  </span>
                </div>
              ))}
            </div>
          </motion.div>
        )}

        {/* Score bars */}
        {hasScores && (
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.4 }}
            className="glass-panel mt-8 p-6 md:p-8 rounded-2xl"
          >
            <h3 className="font-display text-lg font-bold tracking-wide mb-5" style={{ color: "var(--text-primary)" }}>
              Базовые категории
            </h3>
            <div className="space-y-4">
              {scoreItems.map((item, i) => {
                const pct = item.max > 0 ? (item.value / item.max) * 100 : 0;
                const barColor = pct >= 70 ? "var(--success)" : pct >= 40 ? "var(--gf-xp)" : "var(--danger)";
                return (
                  <motion.div key={item.label} initial={{ opacity: 0, x: -16 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.5 + i * 0.1 }}>
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>{item.label}</span>
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-mono font-bold" style={{ color: barColor }}>{Math.round(item.value)}</span>
                        <span className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>/ {item.max}</span>
                      </div>
                    </div>
                    <div className="h-3 w-full overflow-hidden rounded-full" style={{ background: "rgba(255,255,255,0.12)" }}>
                      <motion.div
                        className="h-full rounded-full"
                        initial={{ width: 0 }}
                        animate={{ width: `${Math.min(pct, 100)}%` }}
                        transition={{ duration: 0.8, delay: 0.6 + i * 0.1 }}
                        style={{ background: barColor, boxShadow: `0 0 8px ${colorAlpha(barColor, 25)}` }}
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

        {/* Stage-by-stage breakdown with recommendations */}
        {stageProgress && (
          <div className="mt-6">
            <StageBreakdown
              stageProgress={stageProgress}
              resultDetails={(result.score_breakdown as Record<string, unknown> | null)?.result as Record<string, unknown> | undefined}
              callOutcome={((result.score_breakdown as Record<string, unknown> | null)?.call_outcome as string) || undefined}
              emotionTimeline={session.emotion_timeline || undefined}
            />
          </div>
        )}

        {/* Educational script progress report (Sprint 4) */}
        {stageProgress && (
          <div className="mt-6">
            <ScriptProgressReport stageProgress={stageProgress} />
          </div>
        )}

        {/* AI-Coach Section (expanded analysis with citations) */}
        <div className="mt-6">
          <AICoachSection
            sessionId={String(params.id)}
            coachData={result.score_breakdown as Record<string, unknown> | null}
            difficulty={(() => {
              // Extract difficulty from session or default to 5
              const sd = result.score_breakdown as Record<string, unknown> | null;
              return (sd?._session_difficulty as number) ?? 5;
            })()}
          />
        </div>

        {/* AI Recommendations (markdown) — fallback/complement */}
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
            style={{ borderColor: "rgba(212,168,75,0.3)" }}
          >
            <div className="absolute top-0 left-0 right-0 h-[2px]" style={{ background: "linear-gradient(90deg, transparent, var(--gf-xp), transparent)" }} />
            <div className="absolute -top-10 -right-10 w-40 h-40 rounded-full opacity-10 blur-[60px] pointer-events-none" style={{ background: "var(--gf-xp)" }} />

            <div className="flex items-start gap-4 relative z-10">
              <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl" style={{ background: "rgba(212,168,75,0.1)", border: "1px solid rgba(212,168,75,0.2)" }}>
                <Trophy size={22} style={{ color: "var(--gf-xp)" }} />
              </div>

              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <Swords size={14} style={{ color: "var(--gf-xp)" }} />
                  <span className="font-mono text-xs uppercase tracking-widest" style={{ color: "var(--gf-xp)" }}>ЕЖЕНЕДЕЛЬНЫЙ ТУРНИР</span>
                </div>
                <h3 className="font-display text-lg font-bold" style={{ color: "var(--text-primary)" }}>
                  {tournament.tournament.title}
                </h3>
                <p className="text-sm mt-1" style={{ color: "var(--text-secondary)" }}>
                  Отправьте результат этой сессии в турнир и соревнуйтесь за призовые XP!
                </p>

                {/* Prize info */}
                <div className="mt-3 flex items-center gap-4 font-mono text-xs">
                  <span className="flex items-center gap-1" style={{ color: "var(--gf-xp)" }}>
                    <Crown size={12} /> {tournament.tournament.bonus_xp[0]} XP
                  </span>
                  <span className="flex items-center gap-1" style={{ color: "var(--rank-silver)" }}>
                    <Medal size={12} /> {tournament.tournament.bonus_xp[1]} XP
                  </span>
                  <span className="flex items-center gap-1" style={{ color: "var(--rank-bronze)" }}>
                    <Medal size={12} /> {tournament.tournament.bonus_xp[2]} XP
                  </span>
                </div>

                {/* Leaderboard mini (top 3) */}
                {tournament.leaderboard.length > 0 && (
                  <div className="mt-3 flex items-center gap-3">
                    {tournament.leaderboard.slice(0, 3).map((e) => (
                      <span key={e.user_id} className="font-mono text-xs flex items-center gap-1 px-2 py-1 rounded-full"
                        style={{ background: "var(--input-bg)", color: "var(--text-muted)" }}
                      >
                        <Medal size={12} /> {e.full_name.split(" ")[0]} · {Math.round(e.best_score)}
                      </span>
                    ))}
                    {tournament.leaderboard.length > 3 && (
                      <span className="font-mono text-xs" style={{ color: "var(--text-muted)" }}>
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
                    style={{ background: "rgba(61,220,132,0.08)", border: "1px solid rgba(61,220,132,0.2)", color: "var(--success)" }}
                  >
                    <CheckCircle size={16} />
                    Результат отправлен! Попытка {tournamentResult.attempt} · {Math.round(tournamentResult.score)} баллов
                  </motion.div>
                ) : (
                  <div className="mt-4 flex items-center gap-3">
                    <Button onClick={submitToTournament} loading={tournamentSubmitting} icon={<Trophy size={16} />}>
                      Отправить в турнир ({Math.round(totalScore)} баллов)
                    </Button>
                    <span className="font-mono text-xs" style={{ color: "var(--text-muted)" }}>
                      макс. {tournament.tournament.max_attempts} попыток
                    </span>
                  </div>
                )}

                {tournamentError && (
                  <div className="mt-2 flex items-center gap-2 text-xs" style={{ color: "var(--danger)" }}>
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
              <p className="font-mono text-sm uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
                ДИАЛОГ ({messages.length} сообщ.)
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
                className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 font-mono text-xs uppercase tracking-widest transition-colors"
                style={{ background: "var(--input-bg)", color: transcriptCopied ? "var(--success)" : "var(--text-muted)", border: "1px solid var(--border-color)" }}
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
                className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 font-mono text-xs uppercase tracking-widest transition-colors"
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
            {messages.map((msg, idx) => (
              <div
                key={msg.id}
                className={`flex gap-3 rounded-lg p-2 transition-colors ${msg.role === "user" ? "cursor-pointer hover:ring-1 hover:ring-[var(--accent)]" : ""}`}
                style={{ background: msg.role !== "user" ? "var(--input-bg)" : "transparent" }}
                onClick={() => {
                  if (msg.role === "user") {
                    setReplayMessage({ msg, index: idx });
                  }
                }}
                title={msg.role === "user" ? "Нажмите для идеального ответа" : undefined}
              >
                <span
                  className="w-20 shrink-0 font-mono text-sm uppercase"
                  style={{ color: msg.role === "user" ? "var(--accent)" : emotionColor(msg.emotion_state || "") }}
                >
                  {msg.role === "user" ? "ВЫ" : "КЛИЕНТ"}
                </span>
                <div className="flex-1">
                  <p className="text-sm" style={{ color: "var(--text-secondary)" }}>{msg.content}</p>
                  <div className="flex items-center gap-2 mt-1">
                    {msg.emotion_state && (
                      <span className="inline-block rounded-full px-2 py-0.5 text-xs"
                        style={{ background: "var(--accent-muted)", color: emotionColor(msg.emotion_state) }}
                      >
                        {emotionLabelRu(msg.emotion_state)}
                      </span>
                    )}
                    {msg.role === "user" && (
                      <span className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs opacity-50 hover:opacity-100 transition-opacity"
                        style={{ background: "rgba(138,43,226,0.15)", color: "var(--accent)" }}
                      >
                        <Sparkles size={13} /> Разбор
                      </span>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </motion.div>

        {/* Recommendations + CRM */}
        {hasScores && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.7 }}
            className="mt-8 glass-panel rounded-2xl p-6"
          >
            <h3 className="font-display font-semibold text-base mb-4" style={{ color: "var(--text-primary)" }}>
              Что дальше?
            </h3>
            <div className="flex flex-wrap gap-3">
              {totalScore < 70 && (
                <div className="rounded-xl px-4 py-3 text-sm" style={{ background: "rgba(255,180,0,0.08)", color: "var(--warning)", border: "1px solid rgba(255,180,0,0.2)" }}>
                  Рекомендуем повторить сценарий — сфокусируйтесь на слабых местах
                </div>
              )}
              {totalScore >= 85 && (
                <div className="rounded-xl px-4 py-3 text-sm" style={{ background: "rgba(61,220,132,0.08)", color: "var(--success)", border: "1px solid rgba(61,220,132,0.2)" }}>
                  Отличный результат! Попробуйте более сложный сценарий
                </div>
              )}
              <motion.button
                onClick={async () => {
                  if (addedToCRM) return;
                  try {
                    await api.post("/clients", {
                      full_name: (session as unknown as Record<string, string>).character_name || (session as unknown as Record<string, string>).scenario_name || "Клиент из тренировки",
                      source: "training",
                      status: totalScore >= 70 ? "negotiation" : "new",
                      notes: `Тренировка ${new Date(session.started_at).toLocaleDateString("ru")} — ${Math.round(totalScore)} баллов`,
                    });
                    setAddedToCRM(true);
                  } catch {
                    // Client already exists or other error — ignore silently
                  }
                }}
                className="inline-flex items-center justify-center gap-2 font-bold tracking-wide uppercase rounded-xl px-3 py-1.5 text-xs transition-all duration-200"
                style={addedToCRM ? { background: "rgba(61,220,132,0.15)", borderColor: "rgba(61,220,132,0.3)", border: "1px solid rgba(61,220,132,0.3)", color: "var(--success)" } : { background: "var(--glass-bg)", color: "var(--text-primary)", border: "1px solid var(--accent)" }}
                whileTap={{ scale: 0.97 }}
              >
                <Users size={14} />
                {addedToCRM ? "Добавлен в CRM" : "Добавить клиента в CRM"}
              </motion.button>
              {addedToCRM && (
                <Button href="/clients" size="sm" iconRight={<ArrowRight size={14} />}>
                  Открыть CRM
                </Button>
              )}
            </div>
          </motion.div>
        )}

        {/* Actions */}
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.8 }} className="mt-8 flex justify-center gap-3 pb-8">
          <Button
            onClick={async () => {
              const ok = await copyToClipboard(window.location.href);
              if (ok) {
                setCopied(true);
                setTimeout(() => setCopied(false), 2000);
              }
            }}
            icon={copied ? <Check size={16} /> : <Share2 size={16} />}
          >
            {copied ? "Скопировано" : "Поделиться"}
          </Button>
          <Button href="/home" icon={<Home size={16} />}>На главную</Button>
          {(() => {
            const sessionLoose = session as unknown as {
              scenario_id?: string | null;
              real_client_id?: string | null;
              custom_character_id?: string | null;
              custom_params?: Record<string, unknown> | null;
              id: string;
              started_at?: string | null;
            };
            const oldMode =
              (sessionLoose.custom_params?.session_mode as string) || "chat";
            const realClientId = sessionLoose.real_client_id ?? null;
            const customCharId = sessionLoose.custom_character_id ?? null;
            const retrainLabel = oldMode === "call" ? "Повторить звонок" : "Повторить чат";
            const canRetrain = !!(sessionLoose.scenario_id || realClientId || customCharId);
            // 2026-04-23 Sprint 7 (scenario M) — detect legacy sessions
            // created before Zone 1 migration (2026-04-23) that don't
            // carry real_client_id / custom_character_id. On retrain
            // they'll fallback to P3 direct-clone with a freshly
            // generated random client → warn the user so the mismatch
            // isn't a surprise («почему другой клиент?»).
            const ZONE1_CUTOFF = "2026-04-23";
            const isLegacySession = (() => {
              if (realClientId || customCharId) return false;
              if (!sessionLoose.started_at) return true;
              try {
                return sessionLoose.started_at.slice(0, 10) < ZONE1_CUTOFF;
              } catch {
                return false;
              }
            })();

            return (
              <div className="flex flex-col items-center gap-1.5">
                <Button
                  onClick={async () => {
                    if (repeating || !canRetrain) return;
                    // Priority 1: real_client → CRM pit-stop
                    if (realClientId) {
                      router.push(
                        `/clients/${realClientId}?retrain=${oldMode}&from=${sessionLoose.id}`,
                      );
                      return;
                    }
                    // Priority 2: custom_character → SavedTab pit-stop
                    if (customCharId) {
                      router.push(
                        `/training?retrain_from=${sessionLoose.id}&char=${customCharId}`,
                      );
                      return;
                    }
                    // Priority 3: catalog scenario → direct POST clone (no pit-stop)
                    setRepeating(true);
                    try {
                      const newSession = await api.post("/training/sessions", {
                        clone_from_session_id: sessionLoose.id,
                      });
                      if (oldMode === "call") {
                        router.push(`/training/${newSession.id}/call`);
                      } else {
                        router.push(`/training/${newSession.id}`);
                      }
                    } catch {
                      setRepeating(false);
                    }
                  }}
                  disabled={repeating || !canRetrain}
                  loading={repeating}
                  icon={<Repeat size={16} />}
                >
                  {retrainLabel}
                </Button>
                {isLegacySession && canRetrain && (
                  <span
                    className="text-[10px] flex items-center gap-1"
                    style={{ color: "var(--gf-xp)" }}
                    title="Это старая сессия из времён до обновления CRM-привязки — клиент сгенерируется случайно и может отличаться от оригинального."
                  >
                    <AlertTriangle size={10} />
                    Старая сессия — клиент может отличаться
                  </span>
                )}
              </div>
            );
          })()}
          <Button href="/training" variant="primary" iconRight={<ArrowRight size={16} />}>
            Новая тренировка
          </Button>
        </motion.div>
      </div>

      {/* Wave 5: Replay Mode Modal */}
      {replayMessage && (
        <ReplayModal
          sessionId={session.id}
          message={replayMessage.msg}
          messageIndex={replayMessage.index}
          clientMessageBefore={
            replayMessage.index > 0
              ? messages.slice(0, replayMessage.index).reverse().find((m) => m.role === "assistant") ?? null
              : null
          }
          onClose={() => setReplayMessage(null)}
        />
      )}
    </AuthLayout>
  );
}
