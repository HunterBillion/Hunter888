"use client";

import { motion, AnimatePresence } from "framer-motion";
import { Scale, Heart, ArrowRight, Shield, Zap, Lightbulb, Eye, EyeOff, Target } from "lucide-react";
import type { CoachingWhisper } from "@/types";
import { useSessionStore } from "@/stores/useSessionStore";
import { telemetry } from "@/lib/telemetry";

const ICON_MAP: Record<string, typeof Scale> = {
  scale: Scale,
  heart: Heart,
  "arrow-right": ArrowRight,
  shield: Shield,
  zap: Zap,
  // 2026-04-23 Sprint 3: dedicated icon for type="script" whispers
  // — backend emits these when user gets stuck on a stage.
  target: Target,
};

const TYPE_COLORS: Record<string, string> = {
  legal: "rgba(234, 179, 8, 0.15)",
  emotion: "var(--danger-muted)",
  stage: "rgba(34, 197, 94, 0.12)",
  objection: "rgba(139, 92, 246, 0.12)",
  transition: "rgba(59, 130, 246, 0.12)",
  // 2026-04-23 Sprint 3: script-specific hints — brand purple, same
  // palette as ScriptPanel so user immediately recognises the source.
  script: "rgba(120, 92, 220, 0.14)",
};

const TYPE_BORDER_COLORS: Record<string, string> = {
  legal: "rgba(234, 179, 8, 0.3)",
  emotion: "var(--danger-muted)",
  stage: "rgba(34, 197, 94, 0.25)",
  objection: "rgba(139, 92, 246, 0.25)",
  transition: "rgba(59, 130, 246, 0.25)",
  script: "rgba(120, 92, 220, 0.35)",
};

const TYPE_ICON_COLORS: Record<string, string> = {
  legal: "#EAB308",
  emotion: "var(--danger)",
  stage: "var(--success)",
  objection: "var(--accent)",
  transition: "var(--info)",
  script: "var(--accent)",
};

function formatTimeAgo(timestamp: number): string {
  const diff = Math.floor((Date.now() - timestamp) / 1000);
  if (diff < 60) return "только что";
  const min = Math.floor(diff / 60);
  if (min === 1) return "1 мин назад";
  if (min < 5) return `${min} мин назад`;
  return `${min} мин назад`;
}

interface WhisperPanelProps {
  onToggle?: (enabled: boolean) => void;
}

export default function WhisperPanel({ onToggle }: WhisperPanelProps) {
  const whispers = useSessionStore((s) => s.whispers);
  const enabled = useSessionStore((s) => s.whispersEnabled);
  const hintsEnabled = useSessionStore((s) => s.scriptHintsEnabled);

  const handleToggle = () => {
    const next = !enabled;
    useSessionStore.getState().setWhispersEnabled(next);
    onToggle?.(next);
  };

  const handleToggleHints = () => {
    useSessionStore.getState().setScriptHintsEnabled(!hintsEnabled);
  };

  return (
    <div
      className="flex flex-col"
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Lightbulb size={15} style={{ color: "var(--accent)" }} />
          <span className="text-sm font-semibold uppercase tracking-wide" style={{ color: "var(--text-secondary)" }}>
            Коучинг
          </span>
        </div>
        <button
          onClick={handleToggle}
          className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg transition-colors"
          style={{
            background: enabled ? "rgba(34, 197, 94, 0.12)" : "rgba(255, 255, 255, 0.05)",
            color: enabled ? "var(--success)" : "var(--text-muted)",
          }}
          title={enabled ? "Отключить подсказки" : "Включить подсказки"}
        >
          {enabled ? <Eye size={13} /> : <EyeOff size={13} />}
          <span className="text-xs font-medium uppercase">{enabled ? "ВКЛ" : "ВЫКЛ"}</span>
        </button>
      </div>

      {/* Script hints toggle (AI-generated reply suggestions) */}
      <div className="flex items-center justify-between mb-3 pb-3" style={{ borderBottom: "1px solid var(--border-color)" }}>
        <span className="text-xs" style={{ color: "var(--text-muted)" }}>
          Варианты ответа
        </span>
        <button
          onClick={handleToggleHints}
          className="flex items-center gap-1.5 px-2 py-0.5 rounded-lg transition-colors text-[10px] font-medium uppercase"
          style={{
            background: hintsEnabled ? "rgba(107, 77, 199, 0.15)" : "rgba(255, 255, 255, 0.04)",
            color: hintsEnabled ? "var(--accent)" : "var(--text-muted)",
          }}
          title={hintsEnabled ? "Скрыть варианты реплик" : "Показать варианты реплик"}
        >
          {hintsEnabled ? "ВКЛ" : "ВЫКЛ"}
        </button>
      </div>

      {!enabled && (
        <div className="text-xs" style={{ color: "var(--text-muted)", opacity: 0.6 }}>
          Подсказки отключены
        </div>
      )}

      {enabled && whispers.length === 0 && (
        <div className="text-xs" style={{ color: "var(--text-muted)", opacity: 0.6 }}>
          Подсказки появятся по ходу разговора
        </div>
      )}

      <AnimatePresence mode="popLayout">
        {enabled && whispers.map((w, i) => {
          const IconComponent = ICON_MAP[w.icon] || Lightbulb;
          const opacity = i === 0 ? 1 : i === 1 ? 0.6 : 0.35;
          // 2026-04-23 gap-fill: type="script" whispers are educational
          // («вы застряли на этапе N»). We render a small header «Этап N»
          // and make the whole card clickable — click scrolls the main
          // ScriptPanel into view and expands it if collapsed, so the
          // user can see the task / examples for the stuck stage.
          const isScript = w.type === "script";
          const handleClick = isScript
            ? () => {
                telemetry.track("whisper_script_clicked", {
                  stage: Number(w.stage) || undefined,
                });
                // Find the ScriptPanel header by data-attribute (set in
                // ScriptPanel.tsx on the toggle button) and scroll it
                // into view. If body is collapsed, click it to expand.
                if (typeof document === "undefined") return;
                const header = document.querySelector(
                  "[data-script-panel-header]",
                ) as HTMLButtonElement | null;
                if (!header) return;
                header.scrollIntoView({
                  behavior: "smooth",
                  block: "center",
                });
                // If aria-expanded=false, click to open.
                if (header.getAttribute("aria-expanded") === "false") {
                  header.click();
                }
              }
            : undefined;

          const CardTag = isScript ? motion.button : motion.div;

          return (
            <CardTag
              key={`${w.type}-${w.timestamp}`}
              type={isScript ? "button" : undefined}
              onClick={handleClick}
              initial={{ opacity: 0, y: -8, scale: 0.95 }}
              animate={{ opacity, y: 0, scale: 1 }}
              exit={{ opacity: 0, scale: 0.9 }}
              transition={{ duration: 0.3, delay: i * 0.05 }}
              className={`mt-2.5 rounded-lg px-3 py-2.5 text-left w-full ${
                isScript ? "cursor-pointer transition-colors hover:brightness-110" : ""
              }`}
              style={{
                background: TYPE_COLORS[w.type] || "rgba(255,255,255,0.05)",
                border: `1px solid ${TYPE_BORDER_COLORS[w.type] || "rgba(255,255,255,0.1)"}`,
              }}
              aria-label={
                isScript
                  ? `Подсказка по этапу ${w.stage || "скрипта"}: ${w.message}. Нажмите чтобы открыть панель скрипта.`
                  : undefined
              }
            >
              <div className="flex items-start gap-2.5">
                <IconComponent
                  size={16}
                  style={{ color: TYPE_ICON_COLORS[w.type] || "var(--accent)", marginTop: 2, flexShrink: 0 }}
                />
                <div className="flex-1 min-w-0">
                  {/* 2026-04-23 gap-fill: «Этап N» mini-header for
                      script-type whispers — tells the user which stage
                      this hint refers to. */}
                  {isScript && w.stage && (
                    <div
                      className="text-[10px] font-bold uppercase tracking-wider mb-0.5"
                      style={{ color: TYPE_ICON_COLORS[w.type] }}
                    >
                      Этап {w.stage}
                    </div>
                  )}
                  <div className="text-sm leading-relaxed" style={{ color: "var(--text-primary)" }}>
                    {w.message}
                  </div>
                  <div className="mt-1 text-xs uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>
                    {formatTimeAgo(w.timestamp)}
                  </div>
                </div>
              </div>
            </CardTag>
          );
        })}
      </AnimatePresence>
    </div>
  );
}
