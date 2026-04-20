"use client";

import { useEffect, useState, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { Loader2, Shield, ArrowRight, Heart, HeartCrack } from "lucide-react";
import { useWebSocket } from "@/hooks/useWebSocket";
import { Confetti } from "@/components/ui/Confetti";
// 2026-04-20: PageAuthGate удалён из кодовой базы — auth проверяется в
// middleware.ts на уровне всей /pvp/* секции. Обёртка стала no-op.
// Sprint 4 (2026-04-20): shared sfx pack across all 5 Arena modes
import { useSFX } from "@/components/arena/sfx/useSFX";
// Phase A (2026-04-20) — Arena visual parity
import { CoachingCard, type CoachingPayload } from "@/components/arena/reveal/CoachingCard";
import { CountdownOverlay } from "@/components/arena/reveal/CountdownOverlay";
import { ArenaAudioPlayer } from "@/components/pvp/ArenaAudioPlayer";
import { useLifelines } from "@/components/arena/hooks/useLifelines";
import { useSpeechRecognition } from "@/hooks/useSpeechRecognition";
import { themeFor } from "@/components/arena/themes";
import { Mic, MicOff, Lightbulb, SkipForward } from "lucide-react";

interface DuelScore {
  duel: number;
  score: number;
  isLoss: boolean;
  archetype: string;
  difficulty: number;
}

export default function GauntletPageWrapper() {
  return <GauntletPage />;
}

function GauntletPage() {
  const params = useParams();
  const router = useRouter();
  const runId = params.runId as string;

  const [phase, setPhase] = useState<"loading" | "duel" | "duel_result" | "eliminated" | "completed">("loading");
  const [currentDuel, setCurrentDuel] = useState(0);
  const [totalDuels, setTotalDuels] = useState(5);
  const [losses, setLosses] = useState(0);
  const [archetype, setArchetype] = useState("");
  const [archetypeName, setArchetypeName] = useState("");
  const [difficulty, setDifficulty] = useState(5);
  const [timeLeft, setTimeLeft] = useState(600);
  const [messagesLeft, setMessagesLeft] = useState(8);
  const [messages, setMessages] = useState<{ role: string; text: string }[]>([]);
  const [duelScores, setDuelScores] = useState<DuelScore[]>([]);
  const [finalResult, setFinalResult] = useState<any>(null);
  const [confettiTrigger, setConfettiTrigger] = useState(0);
  const [input, setInput] = useState("");
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const sfx = useSFX();

  // Sprint 4 — preload sfx on mount
  useEffect(() => { sfx.prime(); }, [sfx]);

  // Phase A — Arena visual parity (PvE quota: 3 hints / 2 skips / 1 fifty)
  const theme = themeFor("pve");
  const lifelines = useLifelines({
    sessionId: runId || null,
    mode: "pve",
    enabled: !!runId,
  });
  const [coachingOpen, setCoachingOpen] = useState(false);
  const [coachingPayload, setCoachingPayload] = useState<CoachingPayload | null>(null);
  const [countdownOpen, setCountdownOpen] = useState(false);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const speech = useSpeechRecognition({
    lang: "ru-RU",
    onResult: (text) => setInput((prev) => (prev ? `${prev} ${text}`.trim() : text)),
    onInterim: () => void 0,
    onError: () => void 0,
  });
  const micActive = speech.status === "listening" || speech.status === "processing";

  const startTimer = (seconds: number) => {
    if (timerRef.current) clearInterval(timerRef.current);
    setTimeLeft(seconds);
    timerRef.current = setInterval(() => {
      setTimeLeft((prev) => {
        if (prev <= 1) { if (timerRef.current) clearInterval(timerRef.current); return 0; }
        return prev - 1;
      });
    }, 1000);
  };

  useEffect(() => { return () => { if (timerRef.current) clearInterval(timerRef.current); }; }, []);

  const { sendMessage, connectionState } = useWebSocket({
    path: "/ws/pvp",
    onMessage: (data) => {
      const type = data.type as string;
      const d = (data.data || {}) as Record<string, any>;

      switch (type) {
        case "gauntlet.started":
          setTotalDuels(d.total_duels || 5);
          break;

        case "gauntlet.duel_start":
          setPhase("duel");
          setCurrentDuel(d.duel_number || 1);
          setArchetype(d.archetype || "");
          setArchetypeName(d.archetype_name || d.archetype || "");
          setDifficulty(d.difficulty || 5);
          setLosses(d.losses || 0);
          setMessages([]);
          setMessagesLeft(d.message_limit || 8);
          startTimer(d.time_limit || 600);
          setCountdownOpen(true);    // Phase A — pre-duel countdown
          setAudioUrl(null);
          sfx.play("round_start");
          break;

        // Phase A — TTS narration for gauntlet stage
        case "pvp.audio_ready":
          if (typeof d.audio_url === "string") setAudioUrl(d.audio_url);
          break;

        case "duel.message":
          setMessages((prev) => [...prev, { role: d.sender_role || "client", text: d.text || "" }]);
          if (d.sender_role === "seller") setMessagesLeft((prev) => Math.max(0, prev - 1));
          break;

        case "gauntlet.duel_time_up":
          if (timerRef.current) clearInterval(timerRef.current);
          setTimeLeft(0);
          break;

        case "gauntlet.duel_result": {
          if (timerRef.current) clearInterval(timerRef.current);
          setPhase("duel_result");
          setLosses(d.losses || 0);
          const isLoss = Boolean(d.is_loss);
          const scoreVal = d.score?.total || d.score || 0;
          setDuelScores((prev) => [...prev, {
            duel: d.duel_number || currentDuel,
            score: scoreVal,
            isLoss,
            archetype,
            difficulty,
          }]);
          if (isLoss) sfx.play("wrong");
          else sfx.play("correct");
          // Phase A — coaching payload for post-duel CoachingCard
          const coaching = d.coaching as
            | { tip?: string; ideal_reply?: string; key_articles?: string[] }
            | undefined;
          if (coaching && (coaching.tip || coaching.ideal_reply || (coaching.key_articles?.length ?? 0) > 0)) {
            setCoachingPayload({
              tip: String(coaching.tip ?? ""),
              idealReply: String(coaching.ideal_reply ?? ""),
              keyArticles: Array.isArray(coaching.key_articles) ? coaching.key_articles : [],
              flags: Array.isArray(d.flags) ? d.flags : [],
              legalDetails: Array.isArray(d.legal_details) ? (d.legal_details as CoachingPayload["legalDetails"]) : [],
              // score 0-70 → 0-100
              scoreNormalised: Math.round((Number(scoreVal) / 70) * 100),
            });
            setCoachingOpen(true);
          }
          break;
        }

        case "gauntlet.eliminated":
          setPhase("eliminated");
          setFinalResult(d);
          sfx.play("wrong");
          sfx.play("round_end");
          break;

        case "gauntlet.completed":
          setPhase("completed");
          setFinalResult(d);
          if (!d.is_eliminated) {
            setConfettiTrigger((c) => c + 1);
            sfx.play("correct");
          }
          sfx.play("round_end");
          break;
      }
    },
  });

  useEffect(() => {
    if (connectionState === "connected" && phase === "loading") {
      sendMessage({ type: "gauntlet.start", run_id: runId });
    }
  }, [connectionState, phase, runId, sendMessage]);

  const handleSend = () => {
    if (!input.trim() || messagesLeft <= 0) return;
    sendMessage({ type: "duel.message", text: input.trim() });
    setInput("");
  };

  const formatTime = (s: number) => `${Math.floor(s / 60)}:${(s % 60).toString().padStart(2, "0")}`;

  const livesDisplay = Array.from({ length: 2 }, (_, i) => (
    <span key={i}>
      {i < losses
        ? <HeartCrack size={20} style={{ color: "var(--danger)" }} />
        : <Heart size={20} style={{ color: "var(--danger)", fill: "var(--danger)" }} />
      }
    </span>
  ));

  return (
    <div style={{ maxWidth: 720, margin: "0 auto", padding: "1.5rem", minHeight: "100vh" }}>
      <Confetti trigger={confettiTrigger} />

      {/* Header — Phase A: PvE cyan theme accent */}
      <div style={{
        display: "flex", justifyContent: "space-between", alignItems: "center",
        marginBottom: "1.5rem", padding: "0.75rem 1rem",
        background: `linear-gradient(180deg, ${theme.accent}0d 0%, transparent 100%)`,
        borderRadius: 12,
        border: `1px solid ${theme.accent}33`,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <Shield size={20} style={{ color: theme.accent }} />
          <span style={{ fontWeight: 700, color: theme.accent }}>{theme.label}</span>
          <span style={{ fontSize: "0.7rem", color: "var(--text-muted)", letterSpacing: "0.12em", textTransform: "uppercase", marginLeft: 6 }}>
            {theme.tagline}
          </span>
        </div>
        <div style={{ display: "flex", gap: "1rem", alignItems: "center", fontSize: "0.85rem" }}>
          {phase !== "loading" && <>
            <span>Дуэль {currentDuel}/{totalDuels}</span>
            <div style={{ display: "flex", gap: "0.25rem" }}>{livesDisplay}</div>
          </>}
          {phase === "duel" && (
            <>
              <span style={{ color: timeLeft < 60 ? "var(--danger)" : "var(--text-muted)" }}>{formatTime(timeLeft)}</span>
              <span style={{ color: theme.accent }}>{messagesLeft} сообщ.</span>
            </>
          )}
        </div>
      </div>

      {/* Phase A — TTS narration player for the current stage */}
      {phase === "duel" && audioUrl && (
        <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: "0.75rem" }}>
          <ArenaAudioPlayer
            audioUrl={audioUrl}
            label={`ДУЭЛЬ ${currentDuel}`}
            autoplay={true}
          />
        </div>
      )}

      {/* Phase A — lifeline + mic chip bar (PvE: 3 hints / 2 skips / 1 fifty) */}
      {phase === "duel" && (
        <div style={{ display: "flex", gap: "0.5rem", marginBottom: "0.75rem", flexWrap: "wrap" }}>
          {lifelines.counts.hints > 0 && (
            <button
              type="button"
              onClick={() => lifelines.useHint(archetypeName || "Помоги с ответом")}
              style={{
                display: "inline-flex", alignItems: "center", gap: 6,
                padding: "6px 12px", borderRadius: 10,
                background: "#facc1518", color: "#facc15",
                border: "1px solid #facc1533",
                fontSize: "11px", fontWeight: 600,
                letterSpacing: "0.1em", textTransform: "uppercase",
                cursor: "pointer",
              }}
              title="Подсказка"
            >
              <Lightbulb size={12} /> Подсказка
              <span style={{ fontFamily: "monospace", opacity: 0.8 }}>×{lifelines.counts.hints}</span>
            </button>
          )}
          {lifelines.counts.skips > 0 && (
            <button
              type="button"
              onClick={async () => {
                const ok = await lifelines.useSkip();
                if (ok) {
                  setInput("");
                  sendMessage({ type: "duel.message", text: "__skip__" });
                }
              }}
              style={{
                display: "inline-flex", alignItems: "center", gap: 6,
                padding: "6px 12px", borderRadius: 10,
                background: "#94a3b818", color: "#94a3b8",
                border: "1px solid #94a3b833",
                fontSize: "11px", fontWeight: 600,
                letterSpacing: "0.1em", textTransform: "uppercase",
                cursor: "pointer",
              }}
              title="Пропустить ход"
            >
              <SkipForward size={12} /> Пропустить
              <span style={{ fontFamily: "monospace", opacity: 0.8 }}>×{lifelines.counts.skips}</span>
            </button>
          )}
          {/* 2026-04-20: микрофон ВСЕГДА видим, disabled если API нет. */}
          <button
            type="button"
            onClick={() => (micActive ? speech.stopListening() : speech.startListening())}
            disabled={!speech.isSupported}
            title={
              !speech.isSupported
                ? "Голос недоступен — используйте Chrome/Edge на HTTPS"
                : micActive ? "Остановить" : "Говорить голосом"
            }
            aria-label={micActive ? "Остановить микрофон" : "Включить микрофон"}
            style={{
              display: "inline-flex", alignItems: "center", gap: 6,
              padding: "6px 12px", borderRadius: 10,
              background: micActive ? theme.accent : "transparent",
              color: micActive ? "#0b0b14" : theme.accent,
              border: `1px solid ${theme.accent}55`,
              fontSize: "11px", fontWeight: 600,
              letterSpacing: "0.1em", textTransform: "uppercase",
              cursor: speech.isSupported ? "pointer" : "not-allowed",
              marginLeft: "auto",
              opacity: speech.isSupported ? 1 : 0.4,
            }}
          >
            {micActive ? <MicOff size={12} /> : <Mic size={12} />}
            {micActive ? "слушаю…" : "голос"}
          </button>
        </div>
      )}

      {/* Loading */}
      {phase === "loading" && (
        <div style={{ textAlign: "center", padding: "4rem" }}>
          <Loader2 size={32} style={{ animation: "spin 1s linear infinite", color: "var(--accent)" }} />
          <p style={{ color: "var(--text-muted)", marginTop: "1rem" }}>Подключение к Gauntlet...</p>
        </div>
      )}

      {/* Duel: Chat */}
      {phase === "duel" && (
        <div>
          <div style={{
            display: "flex", justifyContent: "space-between",
            marginBottom: "1rem", padding: "0.5rem 0.75rem",
            background: "rgba(99,102,241,0.08)", borderRadius: 8,
            fontSize: "0.85rem",
          }}>
            <span>Архетип: <strong style={{ color: "var(--accent)" }}>{archetypeName}</strong></span>
            <span style={{ color: "var(--warning)" }}>Сложность: {difficulty}/10</span>
          </div>

          <div style={{
            minHeight: 400, maxHeight: 500, overflowY: "auto", padding: "0.5rem",
            background: "rgba(0,0,0,0.2)", borderRadius: 12,
            border: "1px solid rgba(255,255,255,0.06)", marginBottom: "1rem",
          }}>
            {messages.map((m, i) => (
              <div key={i} style={{
                display: "flex", justifyContent: m.role === "seller" ? "flex-end" : "flex-start",
                marginBottom: "0.5rem",
              }}>
                <div style={{
                  maxWidth: "75%", padding: "0.6rem 0.9rem", borderRadius: 12,
                  background: m.role === "seller" ? "var(--accent)" : "rgba(255,255,255,0.06)",
                  color: m.role === "seller" ? "white" : "var(--text-primary)",
                  fontSize: "0.9rem",
                }}>
                  {m.text}
                </div>
              </div>
            ))}
          </div>

          <div style={{ display: "flex", gap: "0.5rem" }}>
            <input
              value={input} onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSend()}
              placeholder="Ваш ответ..." disabled={messagesLeft <= 0}
              style={{
                flex: 1, padding: "0.75rem 1rem", borderRadius: 10,
                background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)",
                color: "var(--text-primary)", fontSize: "0.9rem", outline: "none",
              }}
            />
            <button onClick={handleSend} disabled={!input.trim() || messagesLeft <= 0}
              style={{
                padding: "0.75rem 1.25rem", borderRadius: 10,
                background: "var(--accent)", border: "none", color: "white",
                cursor: "pointer", fontWeight: 600,
                opacity: !input.trim() || messagesLeft <= 0 ? 0.5 : 1,
              }}>
              <ArrowRight size={18} />
            </button>
          </div>
        </div>
      )}

      {/* Duel Result */}
      {phase === "duel_result" && (
        <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }}
          style={{ textAlign: "center", padding: "3rem" }}>
          <h2 style={{ fontSize: "1.3rem", marginBottom: "1rem" }}>Дуэль {currentDuel} завершена</h2>
          {(() => {
            const last = duelScores[duelScores.length - 1];
            return (
              <>
                <div style={{
                  fontSize: "3rem", fontWeight: 700,
                  color: last?.isLoss ? "var(--danger)" : "var(--success)",
                }}>
                  {last?.score ?? 0}
                </div>
                <p style={{
                  color: last?.isLoss ? "var(--danger)" : "var(--success)",
                  fontWeight: 600, marginTop: "0.5rem",
                }}>
                  {last?.isLoss ? "Поражение" : "Победа"}
                </p>
              </>
            );
          })()}

          <div style={{ display: "flex", justifyContent: "center", gap: "0.5rem", marginTop: "1.5rem" }}>
            {duelScores.map((ds, i) => (
              <div key={i} style={{
                width: 50, height: 50, borderRadius: 10, display: "flex", flexDirection: "column",
                alignItems: "center", justifyContent: "center", fontSize: "0.75rem",
                background: ds.isLoss ? "rgba(239,68,68,0.1)" : "rgba(16,185,129,0.1)",
                border: `1px solid ${ds.isLoss ? "rgba(239,68,68,0.3)" : "rgba(16,185,129,0.3)"}`,
              }}>
                <span style={{ fontWeight: 700 }}>{ds.score}</span>
                <span style={{ fontSize: "0.6rem", color: "var(--text-muted)" }}>D{ds.difficulty}</span>
              </div>
            ))}
          </div>
          <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", marginTop: "1.5rem" }}>
            Следующая дуэль начнётся автоматически...
          </p>
        </motion.div>
      )}

      {/* Eliminated */}
      {phase === "eliminated" && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
          style={{ textAlign: "center", padding: "3rem" }}>
          <HeartCrack size={48} style={{ color: "var(--danger)", marginBottom: "1rem" }} />
          <h2 style={{ fontSize: "1.5rem", color: "var(--danger)" }}>Элиминация!</h2>
          <p style={{ color: "var(--text-muted)", marginTop: "0.5rem" }}>
            2 поражения — Gauntlet окончен
          </p>
          <div style={{ fontSize: "2.5rem", fontWeight: 700, marginTop: "1rem" }}>
            {finalResult?.total_score || 0}
          </div>
          <button onClick={() => router.push("/pvp")} style={{
            marginTop: "2rem", padding: "0.75rem 2rem", borderRadius: 10,
            background: "var(--accent)", border: "none", color: "white",
            cursor: "pointer", fontWeight: 600,
          }}>
            Вернуться в лобби
          </button>
        </motion.div>
      )}

      {/* Completed */}
      {phase === "completed" && finalResult && (
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
          style={{ textAlign: "center", padding: "2rem" }}>
          <Shield size={48} style={{ color: "var(--success)", marginBottom: "1rem" }} />
          <h2 style={{ fontSize: "1.5rem" }}>Gauntlet пройден!</h2>
          <div style={{ fontSize: "3.5rem", fontWeight: 800, color: "var(--success)", marginTop: "0.5rem" }}>
            {finalResult.total_score || 0}
          </div>
          <p style={{ color: "var(--text-muted)" }}>
            {finalResult.completed_duels}/{finalResult.total_duels} дуэлей, {losses} поражений
          </p>

          <div style={{ display: "flex", justifyContent: "center", gap: "0.75rem", marginTop: "2rem", flexWrap: "wrap" }}>
            {(finalResult.duel_scores || duelScores.map(d => d.score)).map((score: any, i: number) => (
              <div key={i} style={{
                padding: "0.75rem 1rem", borderRadius: 10, minWidth: 70, textAlign: "center",
                background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.08)",
              }}>
                <div style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Дуэль {i + 1}</div>
                <div style={{ fontSize: "1.2rem", fontWeight: 700 }}>{typeof score === "number" ? score : score?.score || 0}</div>
              </div>
            ))}
          </div>

          {finalResult.rating_bonus && (
            <p style={{ marginTop: "1.5rem", color: "var(--accent)", fontWeight: 600 }}>
              Рейтинг: +{finalResult.rating_bonus}
            </p>
          )}
          {finalResult.ap_earned && (
            <p style={{ color: "var(--warning)" }}>+{finalResult.ap_earned} Arena Points</p>
          )}

          <button onClick={() => router.push("/pvp")} style={{
            marginTop: "2rem", padding: "0.75rem 2rem", borderRadius: 10,
            background: "var(--accent)", border: "none", color: "white",
            cursor: "pointer", fontWeight: 600, fontSize: "0.95rem",
          }}>
            Вернуться в лобби
          </button>
        </motion.div>
      )}

      {/* Phase A overlays */}
      <CountdownOverlay
        open={countdownOpen}
        accentColor={theme.accent}
        label={`ДУЭЛЬ ${currentDuel}`}
        onDone={() => setCountdownOpen(false)}
      />
      <CoachingCard
        open={coachingOpen}
        accentColor={theme.accent}
        payload={coachingPayload}
        onDismiss={() => setCoachingOpen(false)}
      />
    </div>
  );
}
