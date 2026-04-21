"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { Eye, Users, Loader2 } from "lucide-react";
import { BackButton } from "@/components/ui/BackButton";
import { getWsBaseUrl } from "@/lib/public-origin";
import { getToken } from "@/lib/auth";
import AuthLayout from "@/components/layout/AuthLayout";

interface SpectatorMessage {
  role: string;
  content: string;
  round: number;
  timestamp: string;
}

interface SpectatorState {
  duel_id: string;
  player1_name: string;
  player2_name: string;
  round: number;
  spectator_count: number;
  messages: SpectatorMessage[];
}

export default function SpectatorPage() {
  const { matchId } = useParams<{ matchId: string }>();
  const router = useRouter();
  const wsRef = useRef<WebSocket | null>(null);
  const [state, setState] = useState<SpectatorState | null>(null);
  const [messages, setMessages] = useState<SpectatorMessage[]>([]);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!matchId) return;

    const url = `${getWsBaseUrl()}/ws/pvp?mode=spectator&match_id=${matchId}`;

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      // Send auth token as first message (same pattern as other WS endpoints)
      const token = getToken();
      if (token) {
        ws.send(JSON.stringify({ type: "auth", data: { token } }));
      }
      setConnected(true);
    };
    ws.onclose = (event) => {
      setConnected(false);
      if (event.code === 4001 || event.code === 1008) {
        setError("Сессия истекла. Авторизуйтесь заново.");
      }
    };
    ws.onerror = () => setError("Не удалось подключиться к дуэли");

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        switch (msg.type) {
          case "spectator.state":
            setState(msg.data);
            if (msg.data.messages) {
              setMessages(msg.data.messages.map((m: any) => ({
                ...m,
                timestamp: new Date().toISOString(),
              })));
            }
            break;
          case "spectator.message":
            setMessages((prev) => [
              ...prev,
              { ...msg.data, timestamp: new Date().toISOString() },
            ]);
            break;
          case "duel.verdict":
          case "duel.completed":
            setState((prev) => prev ? { ...prev, round: -1 } : prev);
            break;
          case "error":
            setError(msg.data?.message || "Ошибка");
            break;
        }
      } catch {}
    };

    return () => {
      ws.close();
    };
  }, [matchId]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  if (error) {
    return (
      <AuthLayout>
        <div className="flex h-[60vh] flex-col items-center justify-center gap-4">
          <Eye size={48} className="text-[var(--text-muted)] opacity-30" />
          <p className="text-sm text-[var(--text-secondary)]">{error}</p>
          <button
            onClick={() => router.push("/pvp")}
            className="rounded-xl bg-[var(--accent)] px-6 py-2 text-sm text-white"
          >
            Назад в Арену
          </button>
        </div>
      </AuthLayout>
    );
  }

  if (!connected || !state) {
    return (
      <AuthLayout>
        <div className="flex h-[60vh] items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-[var(--accent)]" />
        </div>
      </AuthLayout>
    );
  }

  const managerMessages = messages.filter((m) => m.role === "manager");
  const clientMessages = messages.filter((m) => m.role === "client");

  return (
    <AuthLayout>
    <div className="mx-auto max-w-6xl px-4 py-6">
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <BackButton href="/pvp" />
          <Eye size={24} className="text-[var(--accent)]" />
          <h1 className="text-lg font-bold text-[var(--text-primary)]">
            {state.round === -1 ? "Дуэль завершена" : `Раунд ${state.round}`}
          </h1>
        </div>
        <div className="flex items-center gap-2 text-sm text-[var(--text-secondary)]">
          <Users size={16} />
          <span>{state.spectator_count} зрителей</span>
        </div>
      </div>

      {/* Players header */}
      <div className="mb-4 grid grid-cols-2 gap-4">
        <div className="rounded-xl bg-[var(--accent-muted)] p-3 text-center">
          <p className="text-xs text-[var(--text-muted)]">Продавец</p>
          <p className="font-semibold text-[var(--text-primary)]">{state.player1_name}</p>
        </div>
        <div className="rounded-xl bg-[var(--danger-muted)] p-3 text-center">
          <p className="text-xs text-[var(--text-muted)]">Клиент</p>
          <p className="font-semibold text-[var(--text-primary)]">{state.player2_name}</p>
        </div>
      </div>

      {/* Split-screen chat */}
      <div className="grid grid-cols-2 gap-4" style={{ minHeight: "50vh" }}>
        {/* Manager side */}
        <div className="flex flex-col rounded-xl bg-[var(--bg-secondary)] p-4">
          <h3 className="mb-3 text-xs font-medium uppercase tracking-wider text-[var(--text-muted)]">Продавец</h3>
          <div className="flex-1 space-y-2 overflow-y-auto">
            {managerMessages.map((msg, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                className="rounded-lg bg-[var(--accent-muted)] px-3 py-2 text-sm text-[var(--text-primary)]"
              >
                {msg.content}
              </motion.div>
            ))}
          </div>
        </div>

        {/* Client side */}
        <div className="flex flex-col rounded-xl bg-[var(--bg-secondary)] p-4">
          <h3 className="mb-3 text-xs font-medium uppercase tracking-wider text-[var(--text-muted)]">Клиент</h3>
          <div className="flex-1 space-y-2 overflow-y-auto">
            {clientMessages.map((msg, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, x: 10 }}
                animate={{ opacity: 1, x: 0 }}
                className="rounded-lg bg-[var(--bg-tertiary)] px-3 py-2 text-sm text-[var(--text-primary)]"
              >
                {msg.content}
              </motion.div>
            ))}
          </div>
        </div>
      </div>
      <div ref={chatEndRef} />
    </div>
    </AuthLayout>
  );
}
