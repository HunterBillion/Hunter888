"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  X,
  Loader2,
  Sparkles,
  ArrowRight,
  TrendingUp,
  Shield,
  Brain,
  Zap,
  AlertTriangle,
  CheckCircle2,
} from "lucide-react";
import { api } from "@/lib/api";
import { EMOTION_MAP, type IdealResponseResult, type ChatMessage } from "@/types";

// ─── Props ──────────────────────────────────────────────────────────────────

interface ReplayModalProps {
  sessionId: string;
  message: ChatMessage;
  messageIndex: number;
  /** The client's message preceding this manager reply (if any) */
  clientMessageBefore?: ChatMessage | null;
  onClose: () => void;
}

// ─── Helpers ────────────────────────────────────────────────────────────────

function emotionBadge(state: string | null) {
  if (!state) return null;
  const cfg = EMOTION_MAP[state];
  if (!cfg) return null;
  return (
    <span
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium"
      style={{
        background: `${cfg.color}22`,
        color: cfg.color,
        border: `1px solid ${cfg.color}44`,
      }}
    >
      <span
        className="w-2 h-2 rounded-full"
        style={{ background: cfg.color, boxShadow: `0 0 6px ${cfg.glow}` }}
      />
      {cfg.labelRu}
    </span>
  );
}

function scoreDeltaBadge(delta: number | null) {
  if (delta === null || delta === undefined) return null;
  const isPositive = delta > 0;
  return (
    <span
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-bold"
      style={{
        background: isPositive ? "rgba(0,255,148,0.15)" : "rgba(255,51,51,0.15)",
        color: isPositive ? "var(--neon-green, #00FF94)" : "#FF3333",
        border: `1px solid ${isPositive ? "rgba(0,255,148,0.3)" : "rgba(255,51,51,0.3)"}`,
      }}
    >
      <TrendingUp className="w-3 h-3" />
      {isPositive ? "+" : ""}{delta.toFixed(1)} pts
    </span>
  );
}

// ─── Component ──────────────────────────────────────────────────────────────

export default function ReplayModal({
  sessionId,
  message,
  messageIndex,
  clientMessageBefore,
  onClose,
}: ReplayModalProps) {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<IdealResponseResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Abort in-flight request on unmount
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  const generateIdeal = useCallback(async () => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true);
    setError(null);
    try {
      const data = await api.post<IdealResponseResult>(
        `/training/sessions/${sessionId}/messages/${message.id}/ideal-response`,
        {},
        { signal: controller.signal },
      );
      if (!controller.signal.aborted) {
        setResult(data);
      }
    } catch (e: unknown) {
      if (e instanceof DOMException && e.name === "AbortError") return;
      setError(e instanceof Error ? e.message : "Failed to generate ideal response");
    } finally {
      if (!controller.signal.aborted) {
        setLoading(false);
      }
    }
  }, [sessionId, message.id]);

  // Close on Escape key
  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleEsc);
    return () => window.removeEventListener("keydown", handleEsc);
  }, [onClose]);

  return (
    <AnimatePresence>
      <motion.div
        className="fixed inset-0 z-50 flex items-center justify-center p-4"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
      >
        {/* Backdrop */}
        <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} aria-hidden="true" />

        {/* Modal */}
        <motion.div
          role="dialog"
          aria-modal="true"
          aria-label="Replay Mode — Идеальный ответ"
          className="relative w-full max-w-2xl max-h-[85vh] overflow-y-auto cyber-card"
          initial={{ scale: 0.9, y: 20 }}
          animate={{ scale: 1, y: 0 }}
          exit={{ scale: 0.9, y: 20 }}
          style={{
            background: "linear-gradient(135deg, rgba(15,10,30,0.98), rgba(25,15,45,0.98))",
            border: "1px solid rgba(138,43,226,0.3)",
            borderRadius: "16px",
            padding: "24px",
          }}
        >
          {/* Header */}
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-3">
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center"
                style={{ background: "rgba(138,43,226,0.2)", border: "1px solid rgba(138,43,226,0.4)" }}
              >
                <Sparkles className="w-5 h-5" style={{ color: "var(--accent, #8A2BE2)" }} />
              </div>
              <div>
                <h3 className="text-lg font-bold" style={{ color: "var(--text-primary, #E8E0F0)" }}>
                  Replay Mode
                </h3>
                <p className="text-xs" style={{ color: "var(--text-muted, #8B7FA8)" }}>
                  Реплика #{messageIndex + 1} — Идеальный ответ
                </p>
              </div>
            </div>
            <button
              onClick={onClose}
              aria-label="Закрыть модальное окно"
              className="w-8 h-8 rounded-lg flex items-center justify-center transition-colors hover:bg-white/10"
              style={{ color: "var(--text-muted, #8B7FA8)" }}
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Original message context */}
          {clientMessageBefore && (
            <div className="mb-4">
              <p className="text-xs font-medium mb-1.5" style={{ color: "var(--text-muted, #8B7FA8)" }}>
                Клиент сказал:
              </p>
              <div
                className="rounded-xl p-3 text-sm"
                style={{
                  background: "rgba(59,130,246,0.08)",
                  border: "1px solid rgba(59,130,246,0.2)",
                  color: "var(--text-secondary, #C4B8D9)",
                }}
              >
                {clientMessageBefore.content}
                <div className="mt-1.5">{emotionBadge(clientMessageBefore.emotion_state)}</div>
              </div>
            </div>
          )}

          {/* Manager's original reply */}
          <div className="mb-6">
            <p className="text-xs font-medium mb-1.5" style={{ color: "var(--text-muted, #8B7FA8)" }}>
              Ваш ответ:
            </p>
            <div
              className="rounded-xl p-3 text-sm"
              style={{
                background: "rgba(138,43,226,0.08)",
                border: "1px solid rgba(138,43,226,0.2)",
                color: "var(--text-secondary, #C4B8D9)",
              }}
            >
              {message.content}
            </div>
          </div>

          {/* Generate button (before result) */}
          {!result && !loading && (
            <button
              onClick={generateIdeal}
              className="btn-neon w-full py-3 text-sm font-medium flex items-center justify-center gap-2"
            >
              <Sparkles className="w-4 h-4" />
              Показать идеальный ответ
              <ArrowRight className="w-4 h-4" />
            </button>
          )}

          {/* Loading */}
          {loading && (
            <div className="flex flex-col items-center py-8 gap-3">
              <Loader2
                className="w-8 h-8 animate-spin"
                style={{ color: "var(--accent, #8A2BE2)" }}
              />
              <p className="text-sm" style={{ color: "var(--text-muted, #8B7FA8)" }}>
                AI анализирует контекст и генерирует идеальный ответ...
              </p>
            </div>
          )}

          {/* Error */}
          {error && (
            <div
              className="rounded-xl p-4 text-sm flex items-center gap-2"
              style={{
                background: "rgba(255,51,51,0.1)",
                border: "1px solid rgba(255,51,51,0.3)",
                color: "#FF6666",
              }}
            >
              <AlertTriangle className="w-4 h-4 flex-shrink-0" />
              {error}
            </div>
          )}

          {/* Result */}
          {result && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="space-y-5"
            >
              {/* Ideal response */}
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <Sparkles className="w-4 h-4" style={{ color: "var(--neon-green, #00FF94)" }} />
                  <p className="text-xs font-bold uppercase tracking-wider" style={{ color: "var(--neon-green, #00FF94)" }}>
                    Идеальный ответ
                  </p>
                  {scoreDeltaBadge(result.score_delta)}
                </div>
                <div
                  className="rounded-xl p-4 text-sm leading-relaxed"
                  style={{
                    background: "rgba(0,255,148,0.06)",
                    border: "1px solid rgba(0,255,148,0.2)",
                    color: "var(--text-primary, #E8E0F0)",
                  }}
                >
                  {result.ideal_text}
                </div>
              </div>

              {/* Explanation */}
              {result.explanation && (
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <Brain className="w-4 h-4" style={{ color: "var(--accent, #8A2BE2)" }} />
                    <p className="text-xs font-bold uppercase tracking-wider" style={{ color: "var(--accent, #8A2BE2)" }}>
                      Почему лучше
                    </p>
                  </div>
                  <p
                    className="text-sm leading-relaxed"
                    style={{ color: "var(--text-secondary, #C4B8D9)" }}
                  >
                    {result.explanation}
                  </p>
                </div>
              )}

              {/* Score comparison bar */}
              {result.original_score_estimate !== null && result.ideal_score_estimate !== null && (
                <div
                  className="rounded-xl p-4"
                  style={{
                    background: "rgba(138,43,226,0.06)",
                    border: "1px solid rgba(138,43,226,0.15)",
                  }}
                >
                  <p className="text-xs font-bold uppercase tracking-wider mb-3" style={{ color: "var(--text-muted, #8B7FA8)" }}>
                    Влияние на балл
                  </p>
                  <div className="flex items-center gap-4">
                    <div className="flex-1">
                      <p className="text-xs mb-1" style={{ color: "var(--text-muted, #8B7FA8)" }}>Оригинал</p>
                      <div className="h-2 rounded-full overflow-hidden" style={{ background: "rgba(255,255,255,0.05)" }}>
                        <div
                          className="h-full rounded-full transition-all"
                          style={{
                            width: `${result.original_score_estimate}%`,
                            background: "var(--accent, #8A2BE2)",
                          }}
                        />
                      </div>
                      <p className="text-xs mt-1 font-mono" style={{ color: "var(--text-muted, #8B7FA8)" }}>
                        {result.original_score_estimate.toFixed(1)}/100
                      </p>
                    </div>
                    <ArrowRight className="w-4 h-4 flex-shrink-0" style={{ color: "var(--neon-green, #00FF94)" }} />
                    <div className="flex-1">
                      <p className="text-xs mb-1" style={{ color: "var(--neon-green, #00FF94)" }}>С идеальным</p>
                      <div className="h-2 rounded-full overflow-hidden" style={{ background: "rgba(255,255,255,0.05)" }}>
                        <div
                          className="h-full rounded-full transition-all"
                          style={{
                            width: `${result.ideal_score_estimate}%`,
                            background: "var(--neon-green, #00FF94)",
                          }}
                        />
                      </div>
                      <p className="text-xs mt-1 font-mono" style={{ color: "var(--neon-green, #00FF94)" }}>
                        {result.ideal_score_estimate.toFixed(1)}/100
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {/* Layer impact chips */}
              {result.layer_impact && Object.keys(result.layer_impact).length > 0 && (
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <Zap className="w-4 h-4" style={{ color: "var(--neon-amber, #F59E0B)" }} />
                    <p className="text-xs font-bold uppercase tracking-wider" style={{ color: "var(--neon-amber, #F59E0B)" }}>
                      Влияние по слоям
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {Object.entries(result.layer_impact).map(([layer, delta]) => (
                      <span
                        key={layer}
                        className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-mono font-medium"
                        style={{
                          background: "rgba(245,158,11,0.1)",
                          border: "1px solid rgba(245,158,11,0.25)",
                          color: "var(--neon-amber, #F59E0B)",
                        }}
                      >
                        {layer}: {delta}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Emotion prediction */}
              {result.ideal_emotion_prediction && (
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <TrendingUp className="w-4 h-4" style={{ color: "#60A5FA" }} />
                    <p className="text-xs font-bold uppercase tracking-wider" style={{ color: "#60A5FA" }}>
                      Эмоция клиента
                    </p>
                  </div>
                  <div className="flex items-center gap-3 mb-2">
                    {emotionBadge(result.original_emotion)}
                    <ArrowRight className="w-4 h-4" style={{ color: "var(--text-muted, #8B7FA8)" }} />
                    {emotionBadge(result.ideal_emotion_prediction)}
                  </div>
                  {result.emotion_explanation && (
                    <p className="text-xs" style={{ color: "var(--text-muted, #8B7FA8)" }}>
                      {result.emotion_explanation}
                    </p>
                  )}
                </div>
              )}

              {/* Trap handling */}
              {result.trap_handling && result.trap_handling.length > 0 && (
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <Shield className="w-4 h-4" style={{ color: "#BF55EC" }} />
                    <p className="text-xs font-bold uppercase tracking-wider" style={{ color: "#BF55EC" }}>
                      Ловушки
                    </p>
                  </div>
                  <div className="space-y-2">
                    {result.trap_handling.map((trap, i) => (
                      <div
                        key={i}
                        className="rounded-lg p-3 text-xs"
                        style={{
                          background: "rgba(191,85,236,0.06)",
                          border: "1px solid rgba(191,85,236,0.15)",
                        }}
                      >
                        <div className="flex items-center justify-between mb-1">
                          <span className="font-medium" style={{ color: "var(--text-primary, #E8E0F0)" }}>
                            {trap.trap}
                          </span>
                          <div className="flex items-center gap-2">
                            <span style={{ color: "#FF6666" }}>{trap.original}</span>
                            <ArrowRight className="w-3 h-3" style={{ color: "var(--text-muted)" }} />
                            <span style={{ color: "var(--neon-green, #00FF94)" }}>
                              <CheckCircle2 className="w-3 h-3 inline mr-0.5" />
                              {trap.ideal}
                            </span>
                          </div>
                        </div>
                        {trap.how && (
                          <p style={{ color: "var(--text-muted, #8B7FA8)" }}>{trap.how}</p>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Retry button */}
              <button
                onClick={generateIdeal}
                disabled={loading}
                className="btn-neon w-full py-2.5 text-xs font-medium flex items-center justify-center gap-2 opacity-70 hover:opacity-100 transition-opacity"
              >
                <Sparkles className="w-3.5 h-3.5" />
                Сгенерировать другой вариант
              </button>
            </motion.div>
          )}
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
