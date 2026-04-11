"use client";

/**
 * What-If Panel — allows replaying a training session with alternative responses.
 *
 * Displayed on the results page. User clicks on their message → types alternative →
 * sees how AI client would have responded differently.
 */

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  GitBranch,
  Send,
  Loader2,
  ChevronRight,
  ArrowLeftRight,
} from "lucide-react";
import { api } from "@/lib/api";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  sequenceNumber?: number;
  emotion?: string;
}

interface WhatIfResult {
  alternative: {
    manager_said: string;
    client_would_say: string;
    predicted_emotion: string;
  };
  original: {
    manager_said: string;
    client_said: string | null;
    actual_emotion: string | null;
  };
}

interface WhatIfPanelProps {
  sessionId: string;
  messages: Message[];
}

export default function WhatIfPanel({ sessionId, messages }: WhatIfPanelProps) {
  const [selectedMsgId, setSelectedMsgId] = useState<string | null>(null);
  const [alternativeText, setAlternativeText] = useState("");
  const [results, setResults] = useState<WhatIfResult[]>([]);
  const [loading, setLoading] = useState(false);

  const userMessages = messages.filter((m) => m.role === "user");

  const simulate = async () => {
    if (!selectedMsgId || !alternativeText.trim() || loading) return;
    setLoading(true);
    try {
      const res = await api.post(
        `/training/sessions/${sessionId}/messages/${selectedMsgId}/what-if`,
        { alternative_text: alternativeText.trim() },
      );
      setResults((prev) => [res, ...prev]);
      setAlternativeText("");
    } catch {
      // silently fail
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="rounded-xl bg-[var(--bg-secondary)] p-5">
      <div className="mb-4 flex items-center gap-2">
        <GitBranch size={18} className="text-[var(--accent)]" />
        <h3 className="text-sm font-semibold text-[var(--text-primary)]">Что если?</h3>
        <span className="text-xs text-[var(--text-muted)]">Выберите своё сообщение и напишите альтернативу</span>
      </div>

      {/* User messages list */}
      <div className="mb-4 max-h-[200px] space-y-1.5 overflow-y-auto">
        {userMessages.map((msg) => (
          <button
            key={msg.id}
            onClick={() => setSelectedMsgId(msg.id)}
            className={`w-full rounded-lg px-3 py-2 text-left text-sm transition-colors ${
              selectedMsgId === msg.id
                ? "bg-[var(--accent)]/15 ring-1 ring-[var(--accent)]/30 text-[var(--text-primary)]"
                : "bg-[var(--bg-tertiary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            }`}
          >
            <span className="mr-2 text-xs text-[var(--text-muted)]">[{msg.sequenceNumber}]</span>
            {msg.content.slice(0, 100)}{msg.content.length > 100 ? "..." : ""}
          </button>
        ))}
      </div>

      {/* Alternative input */}
      <AnimatePresence>
        {selectedMsgId && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="mb-4 space-y-2"
          >
            <textarea
              value={alternativeText}
              onChange={(e) => setAlternativeText(e.target.value)}
              placeholder="Что бы вы сказали иначе?"
              rows={2}
              className="w-full resize-none rounded-xl bg-[var(--bg-tertiary)] px-4 py-2.5 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
            />
            <button
              onClick={simulate}
              disabled={!alternativeText.trim() || loading}
              className="flex items-center gap-2 rounded-xl bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
            >
              {loading ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
              Симулировать
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Results */}
      {results.length > 0 && (
        <div className="space-y-3">
          {results.map((r, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="rounded-xl border border-[var(--border)] p-4"
            >
              <div className="mb-3 flex items-center gap-2 text-xs text-[var(--text-muted)]">
                <ArrowLeftRight size={14} />
                Сравнение
              </div>
              <div className="grid grid-cols-2 gap-3">
                {/* Original */}
                <div className="rounded-lg bg-[var(--bg-tertiary)] p-3">
                  <p className="mb-1 text-xs font-medium text-[var(--text-muted)]">Оригинал</p>
                  <p className="mb-2 text-xs text-[var(--text-secondary)]">{r.original.manager_said.slice(0, 80)}...</p>
                  <div className="flex items-center gap-1">
                    <ChevronRight size={12} className="text-[var(--text-muted)]" />
                    <p className="text-xs text-[var(--text-primary)]">{r.original.client_said?.slice(0, 100) || "—"}</p>
                  </div>
                </div>
                {/* Alternative */}
                <div className="rounded-lg bg-[var(--accent)]/5 border border-[var(--accent)]/10 p-3">
                  <p className="mb-1 text-xs font-medium text-[var(--accent)]">Альтернатива</p>
                  <p className="mb-2 text-xs text-[var(--text-secondary)]">{r.alternative.manager_said.slice(0, 80)}...</p>
                  <div className="flex items-center gap-1">
                    <ChevronRight size={12} className="text-[var(--accent)]" />
                    <p className="text-xs text-[var(--text-primary)]">{r.alternative.client_would_say.slice(0, 100)}</p>
                  </div>
                </div>
              </div>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}
