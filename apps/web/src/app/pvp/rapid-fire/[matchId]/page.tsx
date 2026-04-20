"use client";

import { useEffect, useState, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { Loader2, Zap, ArrowRight } from "lucide-react";
import { useWebSocket } from "@/hooks/useWebSocket";
import { DuelChat } from "@/components/pvp/DuelChat";
import { Confetti } from "@/components/ui/Confetti";
import { logger } from "@/lib/logger";
import { PageAuthGate } from "@/components/layout/PageAuthGate";
// Sprint 4 (2026-04-20): shared sfx pack across all 5 Arena modes
import { useSFX } from "@/components/arena/sfx/useSFX";
// Phase A (2026-04-20) — Arena visual parity across 5 modes
import { CoachingCard, type CoachingPayload } from "@/components/arena/reveal/CoachingCard";
import { CountdownOverlay } from "@/components/arena/reveal/CountdownOverlay";
import { ArenaAudioPlayer } from "@/components/pvp/ArenaAudioPlayer";
import { useLifelines } from "@/components/arena/hooks/useLifelines";
import { useSpeechRecognition } from "@/hooks/useSpeechRecognition";
import { themeFor } from "@/components/arena/themes";
import { Mic, MicOff, Lightbulb } from "lucide-react";

interface RoundScore {
  round: number;
  score: number;
  archetype: string;
}

export default function RapidFirePageWrapper() {
  return (
    <PageAuthGate>
      <RapidFirePage />
    </PageAuthGate>
  );
}

function RapidFirePage() {
  const params = useParams();
  const router = useRouter();
  const matchId = params.matchId as string;

  const [phase, setPhase] = useState<"loading" | "round" | "round_result" | "completed">("loading");
  const [currentRound, setCurrentRound] = useState(0);
  const [totalRounds, setTotalRounds] = useState(5);
  const [archetype, setArchetype] = useState("");
  const [archetypeName, setArchetypeName] = useState("");
  const [timeLeft, setTimeLeft] = useState(120);
  const [messagesLeft, setMessagesLeft] = useState(5);
  const [messages, setMessages] = useState<{ role: string; text: string }[]>([]);
  const [roundScores, setRoundScores] = useState<RoundScore[]>([]);
  const [finalResult, setFinalResult] = useState<any>(null);
  const [confettiTrigger, setConfettiTrigger] = useState(0);
  const [input, setInput] = useState("");
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const sfx = useSFX();

  // Sprint 4 — preload sfx on mount
  useEffect(() => { sfx.prime(); }, [sfx]);

  // Phase A — Arena visual parity
  const theme = themeFor("rapid");
  const lifelines = useLifelines({
    sessionId: matchId || null,
    mode: "rapid",
    enabled: !!matchId,
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
        if (prev <= 1) {
          if (timerRef.current) clearInterval(timerRef.current);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
  };

  useEffect(() => {
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, []);

  const { sendMessage, connectionState } = useWebSocket({
    path: "/ws/pvp",
    onMessage: (data) => {
      const type = data.type as string;
      const d = (data.data || {}) as Record<string, any>;

      switch (type) {
        case "rapid.started":
          setTotalRounds(d.total_rounds || 5);
          break;

        case "rapid.round_start":
          setPhase("round");
          setCurrentRound(d.round || 1);
          setArchetype(d.archetype || "");
          setArchetypeName(d.archetype_name || d.archetype || "");
          setMessages([]);
          setMessagesLeft(d.message_limit || 5);
          startTimer(d.time_limit || 120);
          setCountdownOpen(true);      // Phase A — 3..2..1 before round
          setAudioUrl(null);            // reset previous narration
          sfx.play("round_start");
          break;

        // Phase A — render the TTS narration clip as ArenaAudioPlayer
        case "pvp.audio_ready":
          if (typeof d.audio_url === "string") setAudioUrl(d.audio_url);
          break;

        case "duel.message":
          setMessages((prev) => [...prev, { role: d.sender_role || "client", text: d.text || "" }]);
          if (d.sender_role === "seller") {
            setMessagesLeft((prev) => Math.max(0, prev - 1));
          }
          break;

        case "rapid.round_time_up":
          if (timerRef.current) clearInterval(timerRef.current);
          setTimeLeft(0);
          break;

        case "rapid.round_result": {
          if (timerRef.current) clearInterval(timerRef.current);
          setPhase("round_result");
          const scoreTotal = d.score?.total || d.score || 0;
          setRoundScores((prev) => [...prev, {
            round: d.round || currentRound,
            score: scoreTotal,
            archetype: archetype,
          }]);
          // Score-tiered cue: good runs feel rewarding
          if (scoreTotal >= 70) sfx.play("correct");
          else if (scoreTotal < 40) sfx.play("wrong");
          else sfx.play("round_end");
          // Phase A — coaching payload (embedded in score dict by backend)
          const coaching = d.score?.coaching as
            | { tip?: string; ideal_reply?: string; key_articles?: string[] }
            | undefined;
          if (coaching && (coaching.tip || coaching.ideal_reply || (coaching.key_articles?.length ?? 0) > 0)) {
            setCoachingPayload({
              tip: String(coaching.tip ?? ""),
              idealReply: String(coaching.ideal_reply ?? ""),
              keyArticles: Array.isArray(coaching.key_articles) ? coaching.key_articles : [],
              flags: Array.isArray(d.score?.flags) ? d.score.flags : [],
              legalDetails: Array.isArray(d.score?.legal_details) ? (d.score.legal_details as CoachingPayload["legalDetails"]) : [],
              // scoreTotal is 0-20 scale → normalise to 0-100
              scoreNormalised: Math.round((scoreTotal / 20) * 100),
            });
            setCoachingOpen(true);
          }
          break;
        }

        case "rapid.completed":
          setPhase("completed");
          setFinalResult(d);
          setConfettiTrigger((c) => c + 1);
          sfx.play("correct");
          sfx.play("round_end");
          break;
      }
    },
  });

  // Start the match once connected
  useEffect(() => {
    if (connectionState === "connected" && phase === "loading") {
      sendMessage({ type: "rapid_fire.start", match_id: matchId });
    }
  }, [connectionState, phase, matchId, sendMessage]);

  const handleSend = () => {
    if (!input.trim() || messagesLeft <= 0) return;
    sendMessage({ type: "duel.message", text: input.trim() });
    setInput("");
  };

  const formatTime = (s: number) => `${Math.floor(s / 60)}:${(s % 60).toString().padStart(2, "0")}`;

  return (
    <div style={{ maxWidth: 720, margin: "0 auto", padding: "1.5rem", minHeight: "100vh" }}>
      <Confetti trigger={confettiTrigger} />

      {/* Header — Phase A uses mode theme accent (rapid = yellow) */}
      <div style={{
        display: "flex", justifyContent: "space-between", alignItems: "center",
        marginBottom: "1.5rem", padding: "0.75rem 1rem",
        background: `linear-gradient(180deg, ${theme.accent}0d 0%, transparent 100%)`,
        borderRadius: 12,
        border: `1px solid ${theme.accent}33`,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <Zap size={20} style={{ color: theme.accent }} />
          <span style={{ fontWeight: 700, fontSize: "1rem", color: theme.accent }}>{theme.label}</span>
          <span style={{ fontSize: "0.7rem", color: "var(--text-muted)", letterSpacing: "0.12em", textTransform: "uppercase", marginLeft: 6 }}>
            {theme.tagline}
          </span>
        </div>
        {phase === "round" && (
          <div style={{ display: "flex", gap: "1rem", alignItems: "center", fontSize: "0.85rem" }}>
            <span>Раунд {currentRound}/{totalRounds}</span>
            <span style={{ color: timeLeft < 30 ? "var(--danger)" : "var(--text-muted)" }}>
              {formatTime(timeLeft)}
            </span>
            <span style={{ color: theme.accent }}>{messagesLeft} сообщ.</span>
          </div>
        )}
      </div>

      {/* Phase A — floating TTS narration for the current round */}
      {phase === "round" && audioUrl && (
        <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: "0.75rem" }}>
          <ArenaAudioPlayer
            audioUrl={audioUrl}
            label={`РАУНД ${currentRound}`}
            autoplay={true}
          />
        </div>
      )}

      {/* Phase A — lifeline + mic chip bar */}
      {phase === "round" && (
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
          <Loader2 size={32} style={{ animation: "spin 1s linear infinite", color: "var(--warning)" }} />
          <p style={{ color: "var(--text-muted)", marginTop: "1rem" }}>Подключение к Rapid Fire...</p>
        </div>
      )}

      {/* Round: Chat */}
      {phase === "round" && (
        <div>
          <div style={{
            textAlign: "center", marginBottom: "1rem", padding: "0.5rem",
            background: "rgba(245,158,11,0.08)", borderRadius: 8,
            fontSize: "0.85rem", color: "var(--warning)",
          }}>
            Архетип: <strong>{archetypeName}</strong>
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
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSend()}
              placeholder="Ваш ответ..."
              disabled={messagesLeft <= 0}
              style={{
                flex: 1, padding: "0.75rem 1rem", borderRadius: 10,
                background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)",
                color: "var(--text-primary)", fontSize: "0.9rem", outline: "none",
              }}
            />
            <button
              onClick={handleSend}
              disabled={!input.trim() || messagesLeft <= 0}
              style={{
                padding: "0.75rem 1.25rem", borderRadius: 10,
                background: "var(--accent)", border: "none", color: "white",
                cursor: "pointer", fontWeight: 600,
                opacity: !input.trim() || messagesLeft <= 0 ? 0.5 : 1,
              }}
            >
              <ArrowRight size={18} />
            </button>
          </div>
        </div>
      )}

      {/* Round Result */}
      {phase === "round_result" && (
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          style={{ textAlign: "center", padding: "3rem" }}
        >
          <h2 style={{ fontSize: "1.3rem", marginBottom: "1rem" }}>
            Раунд {currentRound} завершён
          </h2>
          <div style={{
            fontSize: "3rem", fontWeight: 700,
            color: (roundScores[roundScores.length - 1]?.score ?? 0) >= 60 ? "var(--success)" : "var(--warning)",
          }}>
            {roundScores[roundScores.length - 1]?.score ?? 0}
          </div>
          <p style={{ color: "var(--text-muted)", fontSize: "0.85rem", marginTop: "0.5rem" }}>
            Архетип: {archetypeName}
          </p>

          {/* Mini scoreboard */}
          <div style={{ display: "flex", justifyContent: "center", gap: "0.5rem", marginTop: "1.5rem" }}>
            {roundScores.map((rs, i) => (
              <div key={i} style={{
                width: 40, height: 40, borderRadius: 8, display: "flex",
                alignItems: "center", justifyContent: "center", fontWeight: 700, fontSize: "0.8rem",
                background: rs.score >= 60 ? "rgba(16,185,129,0.15)" : "rgba(245,158,11,0.15)",
                color: rs.score >= 60 ? "var(--success)" : "var(--warning)",
                border: `1px solid ${rs.score >= 60 ? "rgba(16,185,129,0.3)" : "rgba(245,158,11,0.3)"}`,
              }}>
                {rs.score}
              </div>
            ))}
          </div>

          <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", marginTop: "1.5rem" }}>
            Следующий раунд начнётся автоматически...
          </p>
        </motion.div>
      )}

      {/* Completed */}
      {phase === "completed" && finalResult && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          style={{ textAlign: "center", padding: "2rem" }}
        >
          <Zap size={48} style={{ color: "var(--warning)", marginBottom: "1rem" }} />
          <h2 style={{ fontSize: "1.5rem", marginBottom: "0.5rem" }}>Rapid Fire завершён!</h2>
          <div style={{
            fontSize: "3.5rem", fontWeight: 800,
            color: (finalResult.normalized || 0) >= 70 ? "var(--success)" : "var(--warning)",
          }}>
            {finalResult.normalized || finalResult.total || 0}
          </div>
          <p style={{ color: "var(--text-muted)", marginTop: "0.25rem" }}>
            Нормализованный балл
          </p>

          {/* All round scores */}
          <div style={{ display: "flex", justifyContent: "center", gap: "0.75rem", marginTop: "2rem", flexWrap: "wrap" }}>
            {(finalResult.mini_scores || roundScores).map((rs: any, i: number) => (
              <div key={i} style={{
                padding: "0.75rem 1rem", borderRadius: 10, minWidth: 80,
                background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.08)",
              }}>
                <div style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Раунд {i + 1}</div>
                <div style={{ fontSize: "1.3rem", fontWeight: 700 }}>{rs.score || rs}</div>
              </div>
            ))}
          </div>

          {finalResult.rating_delta && (
            <p style={{ marginTop: "1.5rem", color: "var(--accent)", fontWeight: 600 }}>
              Рейтинг: {finalResult.rating_delta > 0 ? "+" : ""}{finalResult.rating_delta}
            </p>
          )}
          {finalResult.ap_earned && (
            <p style={{ color: "var(--warning)", fontSize: "0.9rem" }}>
              +{finalResult.ap_earned} Arena Points
            </p>
          )}

          <button
            onClick={() => router.push("/pvp")}
            style={{
              marginTop: "2rem", padding: "0.75rem 2rem", borderRadius: 10,
              background: "var(--accent)", border: "none", color: "white",
              cursor: "pointer", fontWeight: 600, fontSize: "0.95rem",
            }}
          >
            Вернуться в лобби
          </button>
        </motion.div>
      )}

      {/* Phase A overlays: countdown + coaching */}
      <CountdownOverlay
        open={countdownOpen}
        accentColor={theme.accent}
        label={`РАУНД ${currentRound}`}
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
