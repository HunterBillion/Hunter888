"use client";

import { useEffect, useState, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { Loader2, Users, ArrowRight, Clock } from "lucide-react";
import { useWebSocket } from "@/hooks/useWebSocket";
import { Confetti } from "@/components/ui/Confetti";
import { PageAuthGate } from "@/components/layout/PageAuthGate";

export default function TeamBattlePageWrapper() {
  return (
    <PageAuthGate>
      <TeamBattlePage />
    </PageAuthGate>
  );
}

function TeamBattlePage() {
  const params = useParams();
  const router = useRouter();
  const teamId = params.teamId as string;

  const [phase, setPhase] = useState<"loading" | "waiting" | "ready" | "battle" | "scoring" | "completed">("loading");
  const [archetype, setArchetype] = useState("");
  const [archetypeName, setArchetypeName] = useState("");
  const [partnerConnected, setPartnerConnected] = useState(false);
  const [timeLeft, setTimeLeft] = useState(600);
  const [messagesLeft, setMessagesLeft] = useState(8);
  const [messages, setMessages] = useState<{ role: string; text: string }[]>([]);
  const [myScore, setMyScore] = useState<number | null>(null);
  const [waitingForPartner, setWaitingForPartner] = useState(false);
  const [finalResult, setFinalResult] = useState<any>(null);
  const [confettiTrigger, setConfettiTrigger] = useState(0);
  const [input, setInput] = useState("");
  const [waitTimer, setWaitTimer] = useState(120);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const waitTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

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

  const startWaitTimer = () => {
    setWaitTimer(120);
    waitTimerRef.current = setInterval(() => {
      setWaitTimer((prev) => {
        if (prev <= 1) { if (waitTimerRef.current) clearInterval(waitTimerRef.current); return 0; }
        return prev - 1;
      });
    }, 1000);
  };

  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
      if (waitTimerRef.current) clearInterval(waitTimerRef.current);
    };
  }, []);

  const { sendMessage, connectionState } = useWebSocket({
    path: "/ws/pvp",
    onMessage: (data) => {
      const type = data.type as string;
      const d = (data.data || {}) as Record<string, any>;

      switch (type) {
        case "team.waiting":
          setPhase("waiting");
          setArchetype(d.your_archetype || "");
          setArchetypeName(d.archetype_name || d.your_archetype || "");
          setPartnerConnected(d.partner_connected || false);
          if (!d.partner_connected) startWaitTimer();
          break;

        case "team.timeout":
          if (waitTimerRef.current) clearInterval(waitTimerRef.current);
          setPhase("loading");
          router.push("/pvp");
          break;

        case "team.ready":
          if (waitTimerRef.current) clearInterval(waitTimerRef.current);
          setPhase("ready");
          setArchetype(d.your_archetype || archetype);
          setArchetypeName(d.archetype_name || archetypeName);
          setPartnerConnected(true);
          break;

        case "team.round_start":
          setPhase("battle");
          setMessages([]);
          setMessagesLeft(d.message_limit || 8);
          startTimer(d.time_limit || 600);
          break;

        case "duel.message":
          setMessages((prev) => [...prev, { role: d.sender_role || "client", text: d.text || "" }]);
          if (d.sender_role === "seller") setMessagesLeft((prev) => Math.max(0, prev - 1));
          break;

        case "team.time_up":
          if (timerRef.current) clearInterval(timerRef.current);
          setTimeLeft(0);
          break;

        case "team.your_score":
          setPhase("scoring");
          setMyScore(d.score || 0);
          setWaitingForPartner(d.waiting_for_partner || false);
          break;

        case "team.completed":
          setPhase("completed");
          setFinalResult(d);
          setConfettiTrigger((c) => c + 1);
          break;
      }
    },
  });

  useEffect(() => {
    if (connectionState === "connected" && phase === "loading") {
      sendMessage({ type: "team.start", team_id: teamId });
    }
  }, [connectionState, phase, teamId, sendMessage]);

  const handleReady = () => {
    sendMessage({ type: "team.ready_ack" });
  };

  const handleSend = () => {
    if (!input.trim() || messagesLeft <= 0) return;
    sendMessage({ type: "duel.message", text: input.trim() });
    setInput("");
  };

  const formatTime = (s: number) => `${Math.floor(s / 60)}:${(s % 60).toString().padStart(2, "0")}`;

  return (
    <div style={{ maxWidth: 720, margin: "0 auto", padding: "1.5rem", minHeight: "100vh" }}>
      <Confetti trigger={confettiTrigger} />

      {/* Header */}
      <div style={{
        display: "flex", justifyContent: "space-between", alignItems: "center",
        marginBottom: "1.5rem", padding: "0.75rem 1rem",
        background: "rgba(255,255,255,0.03)", borderRadius: 12,
        border: "1px solid rgba(255,255,255,0.08)",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <Users size={20} style={{ color: "var(--success)" }} />
          <span style={{ fontWeight: 700 }}>Командный бой 2v2</span>
        </div>
        {phase === "battle" && (
          <div style={{ display: "flex", gap: "1rem", alignItems: "center", fontSize: "0.85rem" }}>
            <span style={{ color: timeLeft < 60 ? "var(--danger)" : "var(--text-muted)" }}>{formatTime(timeLeft)}</span>
            <span style={{ color: "var(--accent)" }}>{messagesLeft} сообщ.</span>
          </div>
        )}
      </div>

      {/* Loading */}
      {phase === "loading" && (
        <div style={{ textAlign: "center", padding: "4rem" }}>
          <Loader2 size={32} style={{ animation: "spin 1s linear infinite", color: "var(--success)" }} />
          <p style={{ color: "var(--text-muted)", marginTop: "1rem" }}>Подключение...</p>
        </div>
      )}

      {/* Waiting for partner */}
      {phase === "waiting" && (
        <div style={{ textAlign: "center", padding: "3rem" }}>
          <Users size={48} style={{ color: "var(--text-muted)", marginBottom: "1rem" }} />
          <h2 style={{ fontSize: "1.3rem", marginBottom: "0.5rem" }}>Ожидание напарника</h2>
          <p style={{ color: "var(--text-muted)" }}>
            Ваш архетип: <strong style={{ color: "var(--accent)" }}>{archetypeName}</strong>
          </p>
          <div style={{
            marginTop: "1.5rem", display: "flex", alignItems: "center",
            justifyContent: "center", gap: "0.5rem",
          }}>
            <Clock size={16} style={{ color: "var(--warning)" }} />
            <span style={{ color: "var(--warning)", fontSize: "1.2rem", fontWeight: 600 }}>
              {formatTime(waitTimer)}
            </span>
          </div>
          <div style={{
            marginTop: "1rem", display: "flex", gap: "0.5rem", justifyContent: "center",
          }}>
            <div style={{
              width: 12, height: 12, borderRadius: "50%",
              background: "var(--success)",
            }} />
            <span style={{ color: "var(--success)", fontSize: "0.85rem" }}>Вы подключены</span>
            <div style={{
              width: 12, height: 12, borderRadius: "50%", marginLeft: "1rem",
              background: partnerConnected ? "var(--success)" : "rgba(255,255,255,0.15)",
            }} />
            <span style={{ color: partnerConnected ? "var(--success)" : "var(--text-muted)", fontSize: "0.85rem" }}>
              {partnerConnected ? "Напарник онлайн" : "Ожидание..."}
            </span>
          </div>
        </div>
      )}

      {/* Ready */}
      {phase === "ready" && (
        <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }}
          style={{ textAlign: "center", padding: "3rem" }}>
          <h2 style={{ fontSize: "1.3rem", marginBottom: "1rem" }}>Оба игрока готовы!</h2>
          <p style={{ color: "var(--text-muted)" }}>
            Ваш клиент: <strong style={{ color: "var(--accent)" }}>{archetypeName}</strong>
          </p>
          <button onClick={handleReady} style={{
            marginTop: "1.5rem", padding: "0.75rem 2rem", borderRadius: 10,
            background: "var(--success)", border: "none", color: "white",
            cursor: "pointer", fontWeight: 600, fontSize: "1rem",
          }}>
            Начать бой!
          </button>
        </motion.div>
      )}

      {/* Battle: Chat */}
      {phase === "battle" && (
        <div>
          <div style={{
            textAlign: "center", marginBottom: "1rem", padding: "0.5rem",
            background: "rgba(16,185,129,0.08)", borderRadius: 8, fontSize: "0.85rem",
          }}>
            Ваш клиент: <strong style={{ color: "var(--success)" }}>{archetypeName}</strong>
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
                  color: m.role === "seller" ? "white" : "var(--text-primary)", fontSize: "0.9rem",
                }}>
                  {m.text}
                </div>
              </div>
            ))}
          </div>

          <div style={{ display: "flex", gap: "0.5rem" }}>
            <input value={input} onChange={(e) => setInput(e.target.value)}
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

      {/* Scoring — waiting for partner */}
      {phase === "scoring" && (
        <div style={{ textAlign: "center", padding: "3rem" }}>
          <h2 style={{ fontSize: "1.3rem", marginBottom: "1rem" }}>Ваш результат</h2>
          <div style={{ fontSize: "3rem", fontWeight: 700, color: "var(--accent)" }}>
            {myScore}
          </div>
          {waitingForPartner && (
            <div style={{ marginTop: "1.5rem" }}>
              <Loader2 size={20} style={{ animation: "spin 1s linear infinite", color: "var(--text-muted)" }} />
              <p style={{ color: "var(--text-muted)", marginTop: "0.5rem" }}>
                Ожидание результата напарника...
              </p>
            </div>
          )}
        </div>
      )}

      {/* Completed */}
      {phase === "completed" && finalResult && (
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
          style={{ textAlign: "center", padding: "2rem" }}>
          <Users size={48} style={{ color: "var(--success)", marginBottom: "1rem" }} />
          <h2 style={{ fontSize: "1.5rem" }}>Командный бой завершён!</h2>

          <div style={{
            display: "flex", justifyContent: "center", gap: "2rem", marginTop: "2rem",
          }}>
            <div>
              <div style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>Вы</div>
              <div style={{ fontSize: "2rem", fontWeight: 700, color: "var(--accent)" }}>
                {finalResult.your_score || 0}
              </div>
            </div>
            <div>
              <div style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>Напарник</div>
              <div style={{ fontSize: "2rem", fontWeight: 700, color: "var(--accent)" }}>
                {finalResult.partner_score || 0}
              </div>
            </div>
          </div>

          <div style={{
            marginTop: "1.5rem", padding: "1rem", borderRadius: 12,
            background: "rgba(16,185,129,0.08)", border: "1px solid rgba(16,185,129,0.2)",
          }}>
            <div style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>Командный балл</div>
            <div style={{ fontSize: "3rem", fontWeight: 800, color: "var(--success)" }}>
              {finalResult.team_score || 0}
            </div>
          </div>

          {finalResult.archetypes && (
            <p style={{ color: "var(--text-muted)", fontSize: "0.85rem", marginTop: "1rem" }}>
              Архетипы: {finalResult.archetypes.join(" + ")}
            </p>
          )}

          {finalResult.ap_earned && (
            <p style={{ color: "var(--warning)", marginTop: "0.5rem" }}>
              +{finalResult.ap_earned} Arena Points
            </p>
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
    </div>
  );
}
