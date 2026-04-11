"use client";

import { useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  GraduationCap,
  MessageCircle,
  ChevronDown,
  ChevronUp,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  TrendingUp,
  Send,
  Loader2,
  Quote,
} from "lucide-react";
import { api } from "@/lib/api";

// ─── Types ──────────────────────────────────────────────────────────────────

interface CitedMoment {
  message_index: number;
  manager_said: string;
  problem: string;
  better_response: string;
  category: string;
  stage: string;
}

interface StageAnalysisItem {
  stage: string;
  passed: boolean;
  quality: "good" | "weak" | "skipped";
  note: string;
}

interface CoachData {
  cited_moments?: CitedMoment[];
  stage_analysis?: StageAnalysisItem[];
  historical_patterns?: string[];
  summary?: string;
  strengths?: string[];
  weaknesses?: string[];
  recommendations?: string[];
}

interface AICoachSectionProps {
  sessionId: string;
  coachData: CoachData | null;
  difficulty: number; // 1-10, coach chat only for <= 6
}

// ─── Stage label mapping ────────────────────────────────────────────────────

const STAGE_LABELS: Record<string, string> = {
  greeting: "Приветствие",
  contact: "Контакт",
  qualification: "Квалификация",
  presentation: "Презентация",
  objections: "Возражения",
  appointment: "Встреча",
  closing: "Закрытие",
};

const QUALITY_CONFIG = {
  good: { color: "var(--success)", icon: CheckCircle2, label: "Хорошо" },
  weak: { color: "var(--warning)", icon: AlertTriangle, label: "Слабо" },
  skipped: { color: "var(--danger)", icon: XCircle, label: "Пропущен" },
};

// ─── Component ──────────────────────────────────────────────────────────────

export default function AICoachSection({ sessionId, coachData, difficulty }: AICoachSectionProps) {
  const [expanded, setExpanded] = useState(true);
  const [chatMessages, setChatMessages] = useState<Array<{ role: "user" | "coach"; text: string }>>([]);
  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);

  const canChat = difficulty <= 6;

  const handleAskCoach = useCallback(async () => {
    const q = chatInput.trim();
    if (!q || chatLoading) return;

    setChatMessages((prev) => [...prev, { role: "user", text: q }]);
    setChatInput("");
    setChatLoading(true);

    try {
      const res = await api.post(`/training/sessions/${sessionId}/coach`, {
        question: q,
      });
      setChatMessages((prev) => [...prev, { role: "coach", text: res.answer }]);
    } catch {
      setChatMessages((prev) => [
        ...prev,
        { role: "coach", text: "AI-Coach временно недоступен. Попробуйте позже." },
      ]);
    } finally {
      setChatLoading(false);
    }
  }, [chatInput, chatLoading, sessionId]);

  if (!coachData) return null;

  // Coach data fields are stored with _ prefix in scoring_details
  const raw = coachData as Record<string, unknown>;
  const cited_moments = (raw._cited_moments ?? raw.cited_moments ?? []) as CitedMoment[];
  const stage_analysis = (raw._stage_analysis ?? raw.stage_analysis ?? []) as StageAnalysisItem[];
  const historical_patterns = (raw._historical_patterns ?? raw.historical_patterns ?? []) as string[];

  const hasCited = cited_moments.length > 0;
  const hasStageAnalysis = stage_analysis.length > 0;
  const hasPatterns = historical_patterns.length > 0;

  if (!hasCited && !hasStageAnalysis && !hasPatterns) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-panel rounded-2xl p-6 md:p-8"
    >
      {/* Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between border-b pb-3 mb-4"
        style={{ borderColor: "var(--border-color)" }}
      >
        <h2 className="font-display text-lg tracking-widest flex items-center gap-2" style={{ color: "var(--text-primary)" }}>
          <GraduationCap size={20} style={{ color: "var(--accent)" }} />
          AI-COACH РАЗБОР
        </h2>
        {expanded ? <ChevronUp size={18} style={{ color: "var(--text-muted)" }} /> : <ChevronDown size={18} style={{ color: "var(--text-muted)" }} />}
      </button>

      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            {/* Stage Analysis */}
            {hasStageAnalysis && (
              <div className="mb-6">
                <h3 className="font-mono text-xs uppercase tracking-widest mb-3" style={{ color: "var(--text-muted)" }}>
                  АНАЛИЗ ПО СТАДИЯМ
                </h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {stage_analysis.map((sa, i) => {
                    const cfg = QUALITY_CONFIG[sa.quality] || QUALITY_CONFIG.weak;
                    const Icon = cfg.icon;
                    return (
                      <div
                        key={i}
                        className="flex items-start gap-2 rounded-lg px-3 py-2"
                        style={{
                          background: `color-mix(in srgb, ${cfg.color} 3%, transparent)`,
                          border: `1px solid color-mix(in srgb, ${cfg.color} 12%, transparent)`,
                        }}
                      >
                        <Icon size={14} className="flex-shrink-0 mt-0.5" style={{ color: cfg.color }} />
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-xs font-medium" style={{ color: "var(--text-primary)" }}>
                              {STAGE_LABELS[sa.stage] || sa.stage}
                            </span>
                            <span className="text-xs font-mono px-1 rounded" style={{ background: `color-mix(in srgb, ${cfg.color} 8%, transparent)`, color: cfg.color }}>
                              {cfg.label}
                            </span>
                          </div>
                          <p className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>{sa.note}</p>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Cited Moments */}
            {hasCited && (
              <div className="mb-6">
                <h3 className="font-mono text-xs uppercase tracking-widest mb-3 flex items-center gap-1.5" style={{ color: "var(--text-muted)" }}>
                  <Quote size={12} />
                  КЛЮЧЕВЫЕ МОМЕНТЫ С РАЗБОРОМ
                </h3>
                <div className="space-y-3">
                  {cited_moments.map((cm, i) => (
                    <motion.div
                      key={i}
                      initial={{ opacity: 0, x: -8 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: i * 0.1 }}
                      className="rounded-xl overflow-hidden"
                      style={{ border: "1px solid rgba(255,255,255,0.06)" }}
                    >
                      {/* What manager said */}
                      <div className="px-4 py-2.5" style={{ background: "rgba(229,72,77,0.05)" }}>
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-xs font-mono uppercase" style={{ color: "#FF6666" }}>
                            Реплика #{cm.message_index} ({STAGE_LABELS[cm.stage] || cm.stage})
                          </span>
                          <span className="text-xs font-mono px-1.5 rounded" style={{ background: "rgba(229,72,77,0.1)", color: "#FF6666" }}>
                            {(cm.category || "general").replace(/_/g, " ")}
                          </span>
                        </div>
                        <p className="text-xs italic" style={{ color: "var(--text-secondary)" }}>
                          &ldquo;{cm.manager_said}&rdquo;
                        </p>
                        <p className="text-xs mt-1" style={{ color: "#FF8888" }}>
                          {cm.problem}
                        </p>
                      </div>
                      {/* Better response */}
                      <div className="px-4 py-2.5" style={{ background: "rgba(61,220,132,0.04)" }}>
                        <span className="text-xs font-mono uppercase" style={{ color: "var(--success)" }}>
                          Лучше сказать:
                        </span>
                        <p className="text-xs mt-0.5" style={{ color: "var(--text-primary)" }}>
                          &ldquo;{cm.better_response}&rdquo;
                        </p>
                      </div>
                    </motion.div>
                  ))}
                </div>
              </div>
            )}

            {/* Historical Patterns */}
            {hasPatterns && (
              <div className="mb-6">
                <h3 className="font-mono text-xs uppercase tracking-widest mb-3 flex items-center gap-1.5" style={{ color: "var(--text-muted)" }}>
                  <TrendingUp size={12} />
                  ПАТТЕРНЫ ИЗ ВАШЕЙ ИСТОРИИ
                </h3>
                <div className="space-y-1.5">
                  {historical_patterns.map((p, i) => (
                    <div key={i} className="flex items-start gap-2 text-xs" style={{ color: "var(--text-secondary)" }}>
                      <span style={{ color: "var(--accent)" }}>{'>'}</span>
                      {p}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Coach Chat (only for easy/medium difficulty) */}
            {canChat && (
              <div className="border-t pt-4" style={{ borderColor: "var(--border-color)" }}>
                <h3 className="font-mono text-xs uppercase tracking-widest mb-3 flex items-center gap-1.5" style={{ color: "var(--text-muted)" }}>
                  <MessageCircle size={12} />
                  СПРОСИТЬ COACH
                </h3>

                {/* Chat history */}
                {chatMessages.length > 0 && (
                  <div className="space-y-2 mb-3 max-h-64 overflow-y-auto">
                    {chatMessages.map((msg, i) => (
                      <div
                        key={i}
                        className={`rounded-lg px-3 py-2 text-xs ${msg.role === "user" ? "ml-8" : "mr-8"}`}
                        style={{
                          background: msg.role === "user" ? "rgba(124,106,232,0.08)" : "rgba(255,255,255,0.03)",
                          border: `1px solid ${msg.role === "user" ? "rgba(124,106,232,0.2)" : "rgba(255,255,255,0.06)"}`,
                          color: "var(--text-secondary)",
                        }}
                      >
                        <span className="text-xs font-mono uppercase block mb-1" style={{ color: msg.role === "user" ? "var(--accent)" : "var(--success)" }}>
                          {msg.role === "user" ? "Вы" : "Coach"}
                        </span>
                        <p className="whitespace-pre-wrap">{msg.text}</p>
                      </div>
                    ))}
                    {chatLoading && (
                      <div className="flex items-center gap-2 text-xs mr-8" style={{ color: "var(--text-muted)" }}>
                        <Loader2 size={12} className="animate-spin" />
                        Coach думает...
                      </div>
                    )}
                  </div>
                )}

                {/* Input */}
                <div className="flex gap-2">
                  <input
                    value={chatInput}
                    onChange={(e) => setChatInput(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleAskCoach()}
                    placeholder="Что мне нужно было сказать на этом моменте?"
                    className="flex-1 rounded-lg px-3 py-2 text-xs outline-none"
                    style={{
                      background: "var(--input-bg)",
                      border: "1px solid var(--border-color)",
                      color: "var(--text-primary)",
                    }}
                    disabled={chatLoading}
                  />
                  <button
                    onClick={handleAskCoach}
                    disabled={chatLoading || !chatInput.trim()}
                    aria-label="Спросить AI-коуча"
                    className="rounded-lg px-3 py-2 transition-all hover:scale-105 active:scale-95 disabled:opacity-40"
                    style={{ background: "var(--accent)", color: "#fff" }}
                  >
                    <Send size={14} />
                  </button>
                </div>
                <p className="text-xs mt-1.5" style={{ color: "var(--text-muted)" }}>
                  Доступно для сценариев сложности 1-6. Спрашивайте про конкретные моменты разговора.
                </p>
              </div>
            )}

            {!canChat && (
              <div className="border-t pt-3 text-center text-xs" style={{ borderColor: "var(--border-color)", color: "var(--text-muted)" }}>
                AI-Coach чат доступен только для лёгких и средних сценариев (1-6).
                На сложных сценариях разбирайтесь самостоятельно.
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
