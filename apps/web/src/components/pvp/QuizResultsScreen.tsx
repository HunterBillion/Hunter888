"use client";

/**
 * QuizResultsScreen — Phase 3 (PR-22). Финальный экран после квиза.
 *
 * Заменяет inline-блок на quiz/[sessionId]/page.tsx (lines 749-1102).
 * Содержит:
 *   - Hero stat-cards: accuracy %, score, streak, avg time/q
 *   - Combo replay: все ответы deck-flying-in (Hearthstone-стиль)
 *   - XP/AP earned animated counter с level-up flash
 *   - Share buttons (Telegram + Twitter)
 *   - CTAs «Сыграть ещё» (primary) + «К арене» (secondary)
 */

import { useEffect, useMemo, useState } from "react";
import { motion, useMotionValue, useTransform, animate, AnimatePresence } from "framer-motion";
import {
  Trophy,
  Target,
  Zap,
  Clock,
  Flame,
  ChevronLeft,
  ArrowRight,
  Send as SendIcon,
  Share2,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Compass,
  Sparkles,
} from "lucide-react";
import type { QuizMessage } from "@/stores/useKnowledgeStore";

interface QuizResultsScreenProps {
  mode: string | null;
  category: string | null;
  score: number;
  correct: number;
  incorrect: number;
  bestStreak: number;
  totalQuestions: number;
  durationSeconds: number;          // суммарное время сессии
  results: Record<string, unknown>;  // backend results bag
  messages: QuizMessage[];
  onPlayAgain: () => void;
  onBackToArena: () => void;
}

type Level = "correct" | "partial" | "off_topic" | "wrong";

const LEVEL_META: Record<Level, { color: string; Icon: typeof CheckCircle2; label: string }> = {
  correct: { color: "var(--success, #22c55e)", Icon: CheckCircle2, label: "Верно" },
  partial: { color: "var(--warning, #f59e0b)", Icon: AlertCircle, label: "Почти" },
  off_topic: { color: "#60a5fa", Icon: Compass, label: "Не по теме" },
  wrong: { color: "var(--danger, #ef4444)", Icon: XCircle, label: "Неверно" },
};

/** Animated number counter — rolls from 0 to target. */
function CounterNumber({
  value,
  duration = 1.4,
  delay = 0,
  format = (n) => Math.round(n).toString(),
}: {
  value: number;
  duration?: number;
  delay?: number;
  format?: (n: number) => string;
}) {
  const mv = useMotionValue(0);
  const display = useTransform(mv, (n) => format(n));
  const [text, setText] = useState(format(0));

  useEffect(() => {
    const unsub = display.on("change", setText);
    const controls = animate(mv, value, { duration, delay, ease: "easeOut" });
    return () => {
      unsub();
      controls.stop();
    };
  }, [value, duration, delay, mv, display]);

  return <>{text}</>;
}

interface StatCardProps {
  icon: typeof Trophy;
  label: string;
  value: number;
  format?: (n: number) => string;
  accent: string;
  delay?: number;
}
function StatCard({ icon: Icon, label, value, format, accent, delay = 0 }: StatCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16, scale: 0.96 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ delay, type: "spring", stiffness: 240, damping: 22 }}
      className="rounded-2xl p-4 relative overflow-hidden"
      style={{
        background: `linear-gradient(135deg, color-mix(in srgb, ${accent} 12%, rgba(255,255,255,0.04)) 0%, rgba(255,255,255,0.02) 100%)`,
        border: `1px solid color-mix(in srgb, ${accent} 30%, transparent)`,
        boxShadow: `0 8px 28px color-mix(in srgb, ${accent} 18%, transparent), inset 0 1px 0 rgba(255,255,255,0.06)`,
        backdropFilter: "blur(20px) saturate(1.2)",
      }}
    >
      <div className="flex items-center gap-2 mb-2" style={{ color: accent }}>
        <Icon size={18} style={{ filter: `drop-shadow(0 0 6px ${accent}88)` }} />
        <span
          className="font-display font-bold uppercase tracking-widest"
          style={{ fontSize: 11, letterSpacing: "0.16em" }}
        >
          {label}
        </span>
      </div>
      <div
        className="font-display font-bold tabular-nums"
        style={{ color: "var(--text-primary)", fontSize: 32, lineHeight: 1, textShadow: `0 0 16px ${accent}33` }}
      >
        <CounterNumber value={value} format={format} delay={delay + 0.2} />
      </div>
    </motion.div>
  );
}

/** One row in the combo-replay deck. */
function ReplayCard({ cell, i }: { cell: { level: Level; question: string; answer: string }; i: number }) {
  const meta = LEVEL_META[cell.level];
  return (
    <motion.li
      initial={{ opacity: 0, x: -32, rotate: -2 }}
      animate={{ opacity: 1, x: 0, rotate: 0 }}
      transition={{ delay: 0.5 + i * 0.06, type: "spring", stiffness: 220, damping: 22 }}
      className="rounded-xl px-3 py-2 flex items-start gap-3"
      style={{
        background: `linear-gradient(135deg, color-mix(in srgb, ${meta.color} 8%, rgba(255,255,255,0.03)) 0%, rgba(255,255,255,0.02) 100%)`,
        border: `1px solid color-mix(in srgb, ${meta.color} 28%, transparent)`,
        boxShadow: `0 4px 12px color-mix(in srgb, ${meta.color} 14%, transparent), inset 0 1px 0 rgba(255,255,255,0.04)`,
      }}
    >
      <div
        className="flex items-center justify-center rounded-lg shrink-0 mt-0.5"
        style={{
          width: 28,
          height: 28,
          background: `linear-gradient(135deg, color-mix(in srgb, ${meta.color} 28%, transparent) 0%, color-mix(in srgb, ${meta.color} 6%, transparent) 100%)`,
          border: `1px solid ${meta.color}55`,
        }}
      >
        <meta.Icon size={15} style={{ color: meta.color, filter: `drop-shadow(0 0 4px ${meta.color})` }} />
      </div>
      <div className="flex-1 min-w-0">
        <div
          className="font-display font-bold uppercase mb-0.5"
          style={{ color: meta.color, fontSize: 10, letterSpacing: "0.14em" }}
        >
          Q{i + 1} · {meta.label}
        </div>
        <div className="line-clamp-2" style={{ color: "var(--text-primary)", fontSize: 12, lineHeight: 1.4 }}>
          {cell.question}
        </div>
        {cell.answer && (
          <div className="line-clamp-1 mt-0.5 font-mono" style={{ color: "var(--text-muted)", fontSize: 11 }}>
            → {cell.answer}
          </div>
        )}
      </div>
    </motion.li>
  );
}

export function QuizResultsScreen({
  mode,
  category: _category, // eslint-disable-line @typescript-eslint/no-unused-vars
  score,
  correct,
  incorrect,
  bestStreak,
  totalQuestions,
  durationSeconds,
  results,
  messages,
  onPlayAgain,
  onBackToArena,
}: QuizResultsScreenProps) {
  const accuracy = totalQuestions > 0 ? Math.round((correct / totalQuestions) * 100) : 0;
  const total = correct + incorrect;
  const avgTime = total > 0 ? Math.round(durationSeconds / total) : 0;

  // Extract XP/AP from results bag (backend shape varies).
  const xp = useMemo(() => {
    const xpInfo = (results.xp_earned as Record<string, unknown> | undefined) ?? {};
    return typeof xpInfo.total === "number" ? xpInfo.total : 0;
  }, [results]);
  const ap = useMemo(() => {
    const apInfo = (results.ap_earned as Record<string, unknown> | undefined) ?? {};
    return typeof apInfo.amount === "number" ? apInfo.amount : 0;
  }, [results]);
  const levelUp = useMemo(() => {
    const xpInfo = (results.xp_earned as Record<string, unknown> | undefined) ?? {};
    return Boolean(xpInfo.level_up);
  }, [results]);

  // Replay timeline.
  const replay = useMemo<{ level: Level; question: string; answer: string }[]>(() => {
    const out: { level: Level; question: string; answer: string }[] = [];
    let lastQ = "";
    let lastA = "";
    for (const m of messages) {
      if (m.type === "question") lastQ = m.content ?? "";
      else if (m.type === "answer") lastA = m.content ?? "";
      else if (m.type === "feedback") {
        const level: Level =
          (m.verdictLevel as Level | undefined) ?? (m.isCorrect ? "correct" : "wrong");
        out.push({ level, question: lastQ, answer: lastA });
      }
    }
    return out;
  }, [messages]);

  const headlineColor =
    accuracy >= 80 ? "var(--success)"
    : accuracy >= 50 ? "var(--warning)"
    : "var(--danger)";
  const headlineLabel =
    accuracy >= 90 ? "Идеально!"
    : accuracy >= 75 ? "Отлично!"
    : accuracy >= 50 ? "Неплохо"
    : "Можно лучше";

  // Share helpers.
  const shareText = `Я набрал ${accuracy}% в квизе ФЗ-127 на Hunter (${correct}/${totalQuestions}, серия ×${bestStreak}). Попробуй и ты!`;
  const shareUrl = typeof window !== "undefined" ? window.location.origin + "/pvp" : "";
  const tgUrl = `https://t.me/share/url?url=${encodeURIComponent(shareUrl)}&text=${encodeURIComponent(shareText)}`;
  const twUrl = `https://twitter.com/intent/tweet?text=${encodeURIComponent(shareText + "\n" + shareUrl)}`;

  return (
    <div
      className="flex-1 overflow-y-auto"
      style={{
        WebkitFontSmoothing: "antialiased",
        MozOsxFontSmoothing: "grayscale",
      } as React.CSSProperties}
    >
      <div className="mx-auto max-w-4xl px-4 sm:px-6 py-6 pb-32 space-y-6">
        {/* ── Hero headline ── */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          className="text-center"
        >
          <motion.div
            initial={{ scale: 0, rotate: -90 }}
            animate={{ scale: 1, rotate: 0 }}
            transition={{ type: "spring", stiffness: 220, damping: 20, delay: 0.1 }}
            className="inline-flex items-center justify-center rounded-full mb-3"
            style={{
              width: 80,
              height: 80,
              background: `linear-gradient(135deg, color-mix(in srgb, ${headlineColor} 28%, transparent) 0%, rgba(0,0,0,0.2) 100%)`,
              border: `1.5px solid ${headlineColor}`,
              boxShadow: `0 0 32px ${headlineColor}88, inset 0 1px 0 rgba(255,255,255,0.14)`,
            }}
          >
            <Trophy size={42} style={{ color: headlineColor, filter: `drop-shadow(0 0 8px ${headlineColor})` }} />
          </motion.div>
          <motion.h1
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.18 }}
            className="font-display font-bold uppercase"
            style={{
              color: headlineColor,
              fontSize: 36,
              letterSpacing: "0.08em",
              textShadow: `0 0 24px ${headlineColor}44`,
              lineHeight: 1.05,
            }}
          >
            {headlineLabel}
          </motion.h1>
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.28 }}
            className="font-mono uppercase tracking-widest mt-2"
            style={{ color: "var(--text-muted)", fontSize: 12, letterSpacing: "0.18em" }}
          >
            {mode === "blitz" || mode === "rapid_blitz" ? "Блиц" : mode === "themed" ? "По теме" : "Сессия"} · итоги
          </motion.p>
        </motion.div>

        {/* ── Stat cards row ── */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <StatCard
            icon={Target}
            label="Точность"
            value={accuracy}
            format={(n) => `${Math.round(n)}%`}
            accent={headlineColor}
            delay={0.05}
          />
          <StatCard
            icon={Trophy}
            label="Очки"
            value={score}
            accent="var(--accent)"
            delay={0.1}
          />
          <StatCard
            icon={Flame}
            label="Серия"
            value={bestStreak}
            format={(n) => `×${Math.round(n)}`}
            accent="var(--warning)"
            delay={0.15}
          />
          <StatCard
            icon={Clock}
            label="Сред. сек/q"
            value={avgTime}
            format={(n) => `${Math.round(n)}s`}
            accent="#60a5fa"
            delay={0.2}
          />
        </div>

        {/* ── XP / AP earned ── */}
        {(xp > 0 || ap > 0) && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
            className="rounded-2xl px-5 py-4 relative overflow-hidden"
            style={{
              background:
                "linear-gradient(135deg, rgba(245,158,11,0.16) 0%, rgba(217,70,239,0.10) 50%, rgba(96,165,250,0.10) 100%)",
              border: "1px solid rgba(245,158,11,0.35)",
              boxShadow: "0 12px 36px rgba(245,158,11,0.18), inset 0 1px 0 rgba(255,255,255,0.08)",
              backdropFilter: "blur(20px) saturate(1.3)",
            }}
          >
            {levelUp && (
              <motion.div
                initial={{ opacity: 0, scale: 0.6 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ delay: 1.4, type: "spring", stiffness: 300, damping: 16 }}
                className="absolute top-2 right-3 inline-flex items-center gap-1 px-2.5 py-1 rounded-full"
                style={{
                  background: "linear-gradient(135deg, var(--gf-xp, #facc15) 0%, var(--warning) 100%)",
                  color: "#1a0f00",
                  border: "1px solid #fff8",
                  boxShadow: "0 0 18px rgba(245,158,11,0.6)",
                  fontSize: 11,
                  fontWeight: 800,
                  letterSpacing: "0.14em",
                }}
              >
                <Sparkles size={12} /> УРОВЕНЬ ↑
              </motion.div>
            )}
            <div className="flex items-center gap-6 flex-wrap">
              {xp > 0 && (
                <div className="flex items-center gap-2">
                  <Zap size={20} style={{ color: "var(--gf-xp, #facc15)", filter: "drop-shadow(0 0 6px #facc15)" }} />
                  <div>
                    <div
                      className="font-display font-bold uppercase tracking-widest"
                      style={{ color: "var(--text-muted)", fontSize: 10, letterSpacing: "0.16em" }}
                    >
                      Опыт
                    </div>
                    <div
                      className="font-display font-bold tabular-nums"
                      style={{ color: "var(--gf-xp, #facc15)", fontSize: 24, lineHeight: 1 }}
                    >
                      +<CounterNumber value={xp} duration={1.6} delay={0.5} /> XP
                    </div>
                  </div>
                </div>
              )}
              {ap > 0 && (
                <div className="flex items-center gap-2">
                  <Trophy size={20} style={{ color: "var(--accent)", filter: "drop-shadow(0 0 6px var(--accent))" }} />
                  <div>
                    <div
                      className="font-display font-bold uppercase tracking-widest"
                      style={{ color: "var(--text-muted)", fontSize: 10, letterSpacing: "0.16em" }}
                    >
                      Arena Points
                    </div>
                    <div
                      className="font-display font-bold tabular-nums"
                      style={{ color: "var(--accent)", fontSize: 24, lineHeight: 1 }}
                    >
                      +<CounterNumber value={ap} duration={1.6} delay={0.7} /> AP
                    </div>
                  </div>
                </div>
              )}
            </div>
          </motion.div>
        )}

        {/* ── Combo replay deck ── */}
        {replay.length > 0 && (
          <div>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.4 }}
              className="font-display font-bold uppercase tracking-widest mb-3"
              style={{ color: "var(--text-muted)", fontSize: 11, letterSpacing: "0.18em" }}
            >
              Реплей · {replay.length} {replay.length === 1 ? "ответ" : replay.length < 5 ? "ответа" : "ответов"}
            </motion.div>
            <ul className="space-y-2">
              <AnimatePresence>
                {replay.map((cell, i) => (
                  <ReplayCard key={i} cell={cell} i={i} />
                ))}
              </AnimatePresence>
            </ul>
          </div>
        )}

        {/* ── Share row ── */}
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.5 + replay.length * 0.06 }}
          className="flex items-center gap-2 flex-wrap"
        >
          <span
            className="font-display font-bold uppercase tracking-widest"
            style={{ color: "var(--text-muted)", fontSize: 10, letterSpacing: "0.18em" }}
          >
            <Share2 size={12} className="inline mr-1.5" />
            Поделиться:
          </span>
          <a
            href={tgUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 font-display font-bold uppercase tracking-wider transition-colors"
            style={{
              fontSize: 11,
              background: "rgba(34,158,217,0.12)",
              border: "1px solid rgba(34,158,217,0.4)",
              color: "#34a3e0",
              letterSpacing: "0.12em",
            }}
          >
            <SendIcon size={11} /> Telegram
          </a>
          <a
            href={twUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 font-display font-bold uppercase tracking-wider transition-colors"
            style={{
              fontSize: 11,
              background: "rgba(255,255,255,0.04)",
              border: "1px solid rgba(255,255,255,0.18)",
              color: "var(--text-primary)",
              letterSpacing: "0.12em",
            }}
          >
            𝕏 Twitter
          </a>
        </motion.div>

        {/* ── CTAs ── */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.55 + replay.length * 0.06 }}
          className="flex items-center gap-3 pt-2"
        >
          <motion.button
            type="button"
            onClick={onBackToArena}
            whileHover={{ x: -2 }}
            whileTap={{ scale: 0.97 }}
            className="inline-flex items-center gap-2 rounded-xl font-display font-bold uppercase tracking-widest"
            style={{
              padding: "12px 18px",
              background: "rgba(255,255,255,0.04)",
              border: "1px solid rgba(255,255,255,0.12)",
              color: "var(--text-secondary)",
              fontSize: 13,
              letterSpacing: "0.16em",
              cursor: "pointer",
              backdropFilter: "blur(20px)",
            }}
          >
            <ChevronLeft size={16} /> К арене
          </motion.button>
          <motion.button
            type="button"
            onClick={onPlayAgain}
            whileHover={{ y: -1 }}
            whileTap={{ scale: 0.97 }}
            className="flex-1 inline-flex items-center justify-center gap-2 rounded-xl font-display font-bold uppercase tracking-widest"
            style={{
              padding: "14px 20px",
              background: `linear-gradient(135deg, var(--accent) 0%, color-mix(in srgb, var(--accent) 78%, black) 100%)`,
              border: "1px solid color-mix(in srgb, var(--accent) 60%, white)",
              color: "#fff",
              boxShadow: "0 8px 28px color-mix(in srgb, var(--accent) 36%, transparent), inset 0 1px 0 rgba(255,255,255,0.22)",
              fontSize: 14,
              letterSpacing: "0.16em",
              cursor: "pointer",
            }}
          >
            Сыграть ещё <ArrowRight size={16} />
          </motion.button>
        </motion.div>
      </div>
    </div>
  );
}
