"use client";

/**
 * DailyDrillCard — 3-minute micro-simulation with inline quick drill,
 * chest reward trigger, and arcade pixel streak animation.
 *
 * States:
 *   - Not started: Pulsing CTA with skill focus
 *   - In progress: Inline 3-reply chat simulation
 *   - Completed: Pixel streak celebration + chest opening
 */

import { useState, useEffect, useCallback, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Zap, CheckCircle2, Flame, Shield, Loader2, Send, Gift } from "lucide-react";
import { api } from "@/lib/api";
import { logger } from "@/lib/logger";

interface DrillConfig {
  drill_id: string;
  skill_focus: string;
  skill_name: string;
  archetype: string;
  title: string;
  focus: string;
  max_exchanges: number;
  already_completed_today: boolean;
}

interface DrillResult {
  xp_earned: number;
  streak_bonus: number;
  drill_streak: number;
  best_drill_streak: number;
  total_drills: number;
  chest_type: string | null;
}

interface ChestReward {
  chest_type: string;
  xp_reward: number;
  ap_reward: number;
  item_reward: string | null;
  item_name: string | null;
  is_rare_drop: boolean;
}

interface FreezeStatus {
  unused_freezes: number;
  can_purchase: boolean;
  cost_ap: number;
}

// ── Pixel Streak Animation ──────────────────────────────────────────────────

function PixelStreakCelebration({ streak, xp }: { streak: number; xp: number }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const W = canvas.width;
    const H = canvas.height;
    const pixels: { x: number; y: number; vx: number; vy: number; color: string; size: number; life: number }[] = [];

    // Generate pixel particles
    const colors = ["#FFD700", "#FF6B35", "#FF4500", "#FFA500", "#FFEA00", "#7C4DFF"];
    for (let i = 0; i < 60; i++) {
      pixels.push({
        x: W / 2 + (Math.random() - 0.5) * 40,
        y: H / 2,
        vx: (Math.random() - 0.5) * 6,
        vy: -Math.random() * 5 - 2,
        color: colors[Math.floor(Math.random() * colors.length)],
        size: Math.random() > 0.7 ? 4 : 3,
        life: 1,
      });
    }

    let frame = 0;
    const animate = () => {
      ctx.clearRect(0, 0, W, H);
      frame++;

      // Draw pixels
      for (const p of pixels) {
        p.x += p.vx;
        p.y += p.vy;
        p.vy += 0.15; // gravity
        p.life -= 0.012;
        if (p.life <= 0) continue;

        ctx.globalAlpha = p.life;
        ctx.fillStyle = p.color;
        // Pixel-perfect squares (no anti-aliasing)
        ctx.fillRect(Math.floor(p.x), Math.floor(p.y), p.size, p.size);
      }

      // Draw streak number (pixel font style)
      ctx.globalAlpha = Math.min(1, frame / 15);
      ctx.fillStyle = "#FFD700";
      ctx.font = "bold 24px monospace";
      ctx.textAlign = "center";
      ctx.fillText(`${streak}`, W / 2, H / 2 - 8);
      ctx.font = "bold 10px monospace";
      ctx.fillStyle = "#FFA500";
      ctx.fillText(streak === 1 ? "DAY" : "DAYS", W / 2, H / 2 + 8);

      // Draw XP badge
      if (frame > 20) {
        ctx.globalAlpha = Math.min(1, (frame - 20) / 10);
        ctx.fillStyle = "#7C4DFF";
        ctx.font = "bold 11px monospace";
        ctx.fillText(`+${xp} XP`, W / 2, H / 2 + 24);
      }

      ctx.globalAlpha = 1;

      if (frame < 90) {
        requestAnimationFrame(animate);
      }
    };
    animate();
  }, [streak, xp]);

  return (
    <canvas
      ref={canvasRef}
      width={200}
      height={80}
      className="mx-auto render-pixel"
    />
  );
}

// ── Main Component ──────────────────────────────────────────────────────────

export default function DailyDrillCard({
  drillStreak = 0,
}: {
  drillStreak?: number;
  onDrillComplete?: (result: DrillResult) => void;
  onStartDrill?: (config: DrillConfig) => void;
}) {
  const [config, setConfig] = useState<DrillConfig | null>(null);
  const [freezeStatus, setFreezeStatus] = useState<FreezeStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [phase, setPhase] = useState<"idle" | "drilling" | "completing" | "celebration" | "chest">("idle");
  const [drillResult, setDrillResult] = useState<DrillResult | null>(null);
  const [chestReward, setChestReward] = useState<ChestReward | null>(null);
  const [userInput, setUserInput] = useState("");
  const [chatMessages, setChatMessages] = useState<{ role: "client" | "manager"; text: string }[]>([]);
  const [exchangeCount, setExchangeCount] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const fetchDrill = useCallback(async () => {
    try {
      const data = await api.get<DrillConfig>("/gamification/daily-drill");
      setConfig(data);
      if (data.already_completed_today) setPhase("idle");
    } catch (err) {
      logger.error("Failed to fetch daily drill:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchFreezeStatus = useCallback(async () => {
    try {
      const data = await api.get<FreezeStatus>("/gamification/streak-freeze");
      setFreezeStatus(data);
    } catch { /* optional */ }
  }, []);

  useEffect(() => {
    fetchDrill();
    fetchFreezeStatus();
  }, [fetchDrill, fetchFreezeStatus]);

  // Quality tracker for each user reply (good/neutral/bad)
  const qualitiesRef = useRef<Array<"good" | "neutral" | "bad">>([]);
  const [lastFeedback, setLastFeedback] = useState<string | null>(null);

  // ── Start inline drill ──
  const handleStartDrill = () => {
    if (!config) return;
    setPhase("drilling");
    setChatMessages([{
      role: "client",
      text: getClientOpener(config.archetype, config.skill_focus),
    }]);
    setExchangeCount(0);
    qualitiesRef.current = [];
    setLastFeedback(null);
    setTimeout(() => inputRef.current?.focus(), 100);
  };

  // ── Send reply in drill ──
  const handleSendReply = async () => {
    if (!userInput.trim() || !config) return;
    const text = userInput.trim();
    setUserInput("");

    const updatedMessages: { role: "client" | "manager"; text: string }[] = [...chatMessages, { role: "manager" as const, text }];
    setChatMessages(updatedMessages);
    const newCount = exchangeCount + 1;
    setExchangeCount(newCount);

    // Ask backend LLM for the client's real reply + quality judgment
    try {
      type DrillReplyResponse = { client_reply: string; quality: "good" | "neutral" | "bad"; feedback: string };
      const resp = await api.post<DrillReplyResponse>("/gamification/daily-drill/reply", {
        archetype: config.archetype,
        skill_focus: config.skill_focus,
        history: updatedMessages.map(m => ({
          role: m.role === "manager" ? "user" : "assistant",
          content: m.text,
        })).slice(0, -1),  // exclude the just-added manager message (sent separately)
        user_message: text,
      });

      qualitiesRef.current.push(resp.quality);
      setLastFeedback(resp.feedback);

      setChatMessages(prev => [...prev, { role: "client", text: resp.client_reply }]);
    } catch (err) {
      logger.error("Drill reply LLM failed:", err);
      // Graceful fallback: keep the old hardcoded reply path alive
      qualitiesRef.current.push("neutral");
      setChatMessages(prev => [...prev, {
        role: "client",
        text: getClientReply(config.archetype, newCount),
      }]);
    }

    // After 3 exchanges, complete drill with real score
    if (newCount >= 3) {
      setPhase("completing");
      try {
        const result = await api.post<DrillResult>("/gamification/daily-drill/complete", {
          qualities: qualitiesRef.current,
        });
        setDrillResult(result);
        setPhase("celebration");

        setTimeout(async () => {
          if (result.chest_type) {
            try {
              const chest = await api.post<ChestReward>("/gamification/chest/open", { chest_type: result.chest_type });
              setChestReward(chest);
              setPhase("chest");
            } catch {
              setPhase("idle");
              fetchDrill();
            }
          } else {
            setPhase("idle");
            fetchDrill();
          }
        }, 3000);
      } catch (err) {
        logger.error("Drill complete failed:", err);
        setPhase("idle");
      }
    }
  };

  const completed = config?.already_completed_today ?? false;
  const streak = drillResult?.drill_streak ?? drillStreak;

  if (loading) {
    return (
      <div className="rounded-xl bg-[var(--bg-secondary)] p-5 animate-pulse">
        <div className="h-4 w-32 rounded bg-[var(--input-bg)] mb-3" />
        <div className="h-10 w-full rounded bg-[var(--input-bg)]" />
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="rounded-xl bg-[var(--bg-secondary)] p-5 relative overflow-hidden"
    >
      {!completed && phase === "idle" && (
        <div className="absolute inset-0 bg-gradient-to-r from-[var(--accent-muted)] to-transparent pointer-events-none" />
      )}

      {/* Header */}
      <div className="flex items-center justify-between mb-3 relative z-10">
        <div className="flex items-center gap-2">
          <Zap size={18} className={completed || phase !== "idle" ? "text-[var(--success)]" : "text-[var(--accent)]"} />
          <h3 className="text-sm font-semibold text-[var(--text-primary)]">
            Утренняя разминка
          </h3>
        </div>
        <div className="flex items-center gap-2">
          {streak > 0 && (
            <div className="flex items-center gap-1 rounded-md bg-[var(--warning-muted)] px-2 py-0.5">
              <Flame size={12} className="text-[var(--warning)]" />
              <span className="text-xs font-bold text-[var(--warning)]">{streak}</span>
            </div>
          )}
          {freezeStatus && freezeStatus.unused_freezes > 0 && (
            <div className="flex items-center gap-1 rounded-md bg-sky-500/10 px-2 py-0.5">
              <Shield size={12} className="text-sky-400" />
              <span className="text-xs font-medium text-sky-400">{freezeStatus.unused_freezes}</span>
            </div>
          )}
        </div>
      </div>

      {/* Content by phase */}
      <div className="relative z-10">
        <AnimatePresence mode="wait">

          {/* IDLE — completed */}
          {(completed && phase === "idle") && (
            <motion.div key="done" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[var(--success-muted)]">
                <CheckCircle2 size={20} className="text-[var(--success)]" />
              </div>
              <div>
                <p className="text-sm font-medium text-[var(--text-primary)]">Разминка пройдена</p>
                <p className="text-xs text-[var(--text-muted)]">
                  +25 XP {streak > 1 ? `(стрик: ${streak} дней)` : ""}
                </p>
              </div>
            </motion.div>
          )}

          {/* IDLE — not started */}
          {(!completed && phase === "idle" && config) && (
            <motion.div key="start" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
              <div className="mb-3">
                <p className="text-sm text-[var(--text-secondary)] mb-1">
                  <span className="font-medium text-[var(--text-primary)]">{config.title}</span>
                  {" "}&middot;{" "}
                  <span className="text-[var(--accent)]">{config.skill_name}</span>
                </p>
                <p className="text-xs text-[var(--text-muted)]">{config.focus}</p>
              </div>
              <button
                onClick={handleStartDrill}
                className="w-full flex items-center justify-center gap-2 rounded-lg bg-[var(--accent)] px-4 py-2.5 text-sm font-semibold text-white transition-all hover:brightness-110 active:scale-[0.98]"
              >
                <Zap size={16} />
                Начать разминку (3 мин)
              </button>
            </motion.div>
          )}

          {/* DRILLING — inline chat */}
          {phase === "drilling" && (
            <motion.div key="drill" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
              <div className="space-y-2 max-h-40 overflow-y-auto mb-3 pr-1">
                {chatMessages.map((msg, i) => (
                  <motion.div
                    key={i}
                    initial={{ opacity: 0, x: msg.role === "manager" ? 20 : -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    className={`flex ${msg.role === "manager" ? "justify-end" : "justify-start"}`}
                  >
                    <div
                      className={`rounded-lg px-3 py-1.5 text-xs max-w-[85%] ${
                        msg.role === "manager"
                          ? "bg-[var(--accent-muted)] text-[var(--text-primary)]"
                          : "bg-[var(--input-bg)] text-[var(--text-secondary)]"
                      }`}
                    >
                      {msg.text}
                    </div>
                  </motion.div>
                ))}
              </div>
              <div className="flex gap-2">
                <input
                  ref={inputRef}
                  value={userInput}
                  onChange={e => setUserInput(e.target.value)}
                  onKeyDown={e => e.key === "Enter" && handleSendReply()}
                  placeholder="Ваш ответ..."
                  className="flex-1 rounded-lg bg-[var(--input-bg)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none focus:ring-1 focus:ring-[var(--accent)]"
                />
                <button
                  onClick={handleSendReply}
                  disabled={!userInput.trim()}
                  className="rounded-lg bg-[var(--accent)] px-3 py-2 text-white disabled:opacity-40"
                >
                  <Send size={14} />
                </button>
              </div>
              {lastFeedback && (
                <p className="text-[10px] mt-2 px-2 py-1 rounded" style={{
                  background: "var(--accent-muted)",
                  color: "var(--text-secondary)",
                }}>
                  💬 {lastFeedback}
                </p>
              )}
              <p className="text-[10px] text-[var(--text-muted)] mt-1 text-center">
                {exchangeCount}/3 ответов
              </p>
            </motion.div>
          )}

          {/* COMPLETING — loading */}
          {phase === "completing" && (
            <motion.div key="completing" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="text-center py-4">
              <Loader2 size={24} className="animate-spin text-[var(--accent)] mx-auto mb-2" />
              <p className="text-sm text-[var(--text-muted)]">Оценка...</p>
            </motion.div>
          )}

          {/* CELEBRATION — pixel streak animation */}
          {phase === "celebration" && drillResult && (
            <motion.div key="celebration" initial={{ opacity: 0, scale: 0.8 }} animate={{ opacity: 1, scale: 1 }} className="text-center py-2">
              <PixelStreakCelebration streak={drillResult.drill_streak} xp={drillResult.xp_earned} />
              <motion.p
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.5 }}
                className="text-xs text-[var(--text-muted)] mt-1"
              >
                {drillResult.chest_type && "Открываем награду..."}
              </motion.p>
            </motion.div>
          )}

          {/* CHEST — reward reveal */}
          {phase === "chest" && chestReward && (
            <motion.div key="chest" initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} className="text-center py-2">
              <motion.div
                initial={{ rotate: -5 }}
                animate={{ rotate: [0, -3, 3, -3, 3, 0] }}
                transition={{ duration: 0.5 }}
                className="text-4xl mb-2"
              >
                <Gift size={40} className="mx-auto text-[var(--warning)]" />
              </motion.div>
              <p className="text-lg font-bold font-mono text-[var(--accent)]">+{chestReward.xp_reward} XP</p>
              {chestReward.ap_reward > 0 && (
                <p className="text-sm font-bold text-[var(--warning)]">+{chestReward.ap_reward} AP</p>
              )}
              {chestReward.item_name && (
                <p className="text-xs text-[var(--warning)] mt-1">{chestReward.item_name}</p>
              )}
              <button
                onClick={() => { setPhase("idle"); fetchDrill(); }}
                className="mt-3 rounded-lg bg-[var(--accent)] px-6 py-2 text-sm font-semibold text-white"
              >
                Забрать
              </button>
            </motion.div>
          )}

        </AnimatePresence>
      </div>
    </motion.div>
  );
}

// ── Helper: client dialogue templates ───────────────────────────────────────

function getClientOpener(archetype: string, skill: string): string {
  const openers: Record<string, string[]> = {
    anxious: ["Здравствуйте... я очень переживаю за свою ситуацию с долгами.", "Мне страшно, что будет с квартирой если я подам на банкротство..."],
    aggressive: ["Слушайте, мне уже звонили 10 раз! Зачем вы опять звоните?!", "Я вас не просил звонить! Что вам надо?"],
    skeptic: ["Ну и зачем мне это банкротство? Очередной развод?", "Вы что, бесплатно работаете? В чём подвох?"],
    passive: ["Ну... не знаю. Может потом перезвоните.", "Я подумаю."],
    desperate: ["Помогите! У меня забирают всё! Коллекторы звонят каждый день!", "Я не знаю что делать, долги растут..."],
    crying: ["*плачет* Я не знаю как мне жить дальше...", "Простите... *всхлип* У меня совсем нет сил..."],
    know_it_all: ["Я сам юрист, знаю 127-ФЗ лучше вас. Что нового скажете?", "Статья 213.4 говорит, что... Вы вообще закон читали?"],
    manipulator: ["А давайте вы мне бесплатно расскажете, а я подумаю.", "Мне другие компании предлагали дешевле."],
    paranoid: ["Откуда у вас мой номер?! Это мошенничество?", "Я не буду ничего подписывать! Вдруг это обман?"],
  };
  const list = openers[archetype] || openers.anxious;
  return list[Math.floor(Math.random() * list.length)] || list[0];
}

function getClientReply(archetype: string, exchange: number): string {
  const replies: Record<string, string[]> = {
    anxious: ["А вы уверены что это безопасно?", "А что скажут на работе?", "Мне правда помогут?"],
    aggressive: ["Ладно, говорите быстрее!", "И сколько это стоит?!", "Хм... ну допустим."],
    skeptic: ["Докажите цифрами.", "А какие гарантии?", "Звучит слишком хорошо."],
    passive: ["Мм... ладно.", "Ну может быть...", "Я не уверен..."],
    desperate: ["Правда?! Вы можете помочь?", "Когда можно начать?", "Я на всё согласен!"],
    crying: ["*успокаивается* Спасибо что слушаете...", "А это правда работает?", "Хорошо, расскажите подробнее..."],
    know_it_all: ["Хм, интересная трактовка.", "А что по статье 446?", "Ладно, убедили."],
    manipulator: ["А можно скидку?", "Ну хорошо, рассказывайте.", "А если я приведу знакомого?"],
    paranoid: ["Ладно, но я запишу разговор.", "А данные точно в безопасности?", "Хм... звучит правдоподобно."],
  };
  const list = replies[archetype] || replies.anxious;
  return list[Math.min(exchange, list.length - 1)] || "Понятно...";
}
