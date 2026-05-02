"use client";

/**
 * SoundSettings — карточка управления звуком на странице /settings.
 *
 * 2026-05-02 (rewrite): унификация стиля. Раньше карточка использовала
 * pixel/arena эстетику (`borderRadius: 0`, `outline: 2px solid`,
 * `boxShadow: "3px 3px 0 0 #000"`, `font-pixel`) и визуально не
 * сочеталась с остальной страницей настроек, построенной на glass-panel
 * + rounded-xl. Теперь оба соседних блока используют одинаковую
 * card-конвенцию (`glass-panel rounded-xl border-radius`), один и тот
 * же тонкий слайдер вместо pixel-thumb, и единый набор CSS-переменных.
 *
 * Поведение не меняется:
 *   - 4 ползунка: Master / SFX / Ambient / UI (0..100)
 *   - Mute-toggle (полностью отключает все звуки)
 *   - Preview-кнопки: тестовый звук категории
 *   - Все значения — в localStorage, синхронизируются между табами через
 *     useSyncExternalStore + custom event "vh-volume-change".
 */

import * as React from "react";
import { motion } from "framer-motion";
import {
  SpeakerHigh, SpeakerSimpleSlash, Headphones, GameController, Bell,
} from "@phosphor-icons/react";
import {
  useSound,
  useVolumes,
  setMasterVolume,
  setCategoryVolume,
  setMutedGlobal,
  isMutedGlobal,
  type SoundName,
} from "@/hooks/useSound";

interface CategorySpec {
  key: "master" | "sfx" | "ambient" | "ui";
  label: string;
  hint: string;
  icon: React.ComponentType<{ size?: number; weight?: "duotone" | "regular" | "fill" | "bold"; style?: React.CSSProperties }>;
  /** Звук-превью при изменении ползунка / по клику на кнопку. */
  preview: SoundName;
  /** CSS-переменная цвета акцента карточки. */
  accent: string;
}

const CATEGORIES: CategorySpec[] = [
  {
    key: "master",
    label: "Общая громкость",
    hint: "Базовый уровень всех звуков",
    icon: SpeakerHigh,
    preview: "ko",
    accent: "var(--accent)",
  },
  {
    key: "sfx",
    label: "Эффекты",
    hint: "Удары, KO, fanfare, heartbeat",
    icon: GameController,
    preview: "hit",
    accent: "var(--danger)",
  },
  {
    key: "ambient",
    label: "Фон арены",
    hint: "Гул и атмосфера сцены",
    icon: Headphones,
    preview: "challenge",
    accent: "var(--magenta, var(--accent))",
  },
  {
    key: "ui",
    label: "Интерфейс",
    hint: "Клики, уведомления, переключения",
    icon: Bell,
    preview: "notification",
    accent: "var(--info)",
  },
];

export function SoundSettings() {
  const volumes = useVolumes();
  const { playSound } = useSound();
  const [muted, setMuted] = React.useState<boolean>(false);

  React.useEffect(() => {
    setMuted(isMutedGlobal());
    const onChange = () => setMuted(isMutedGlobal());
    window.addEventListener("vh-volume-change", onChange);
    window.addEventListener("storage", onChange);
    return () => {
      window.removeEventListener("vh-volume-change", onChange);
      window.removeEventListener("storage", onChange);
    };
  }, []);

  const handleMute = () => {
    setMutedGlobal(!muted);
    setMuted(!muted);
    if (muted) {
      // un-muting — soft confirmation tone
      window.setTimeout(() => playSound("notification"), 50);
    }
  };

  const handleSlide = (cat: CategorySpec, value: number) => {
    if (cat.key === "master") setMasterVolume(value);
    else setCategoryVolume(cat.key, value);
  };

  // Debounced preview: play after 220ms of no change to avoid spamming.
  const previewTimeoutRef = React.useRef<Record<string, ReturnType<typeof setTimeout>>>({});
  const schedulePreview = (cat: CategorySpec) => {
    if (muted) return;
    const existing = previewTimeoutRef.current[cat.key];
    if (existing) clearTimeout(existing);
    previewTimeoutRef.current[cat.key] = setTimeout(() => {
      playSound(cat.preview);
    }, 220);
  };

  const valueOf = (cat: CategorySpec): number => {
    if (cat.key === "master") return volumes.master;
    if (cat.key === "sfx") return volumes.sfx;
    if (cat.key === "ambient") return volumes.ambient;
    if (cat.key === "ui") return volumes.ui;
    return 0;
  };

  return (
    <div className="space-y-3">
      {/* Master mute toggle — single full-width card matching the
          surrounding /settings glass-panel scheme. */}
      <div
        className="glass-panel rounded-xl p-4 flex items-center justify-between"
        style={{ borderColor: muted ? "var(--danger)" : undefined }}
      >
        <div className="flex items-center gap-3">
          {muted ? (
            <SpeakerSimpleSlash weight="duotone" size={22} style={{ color: "var(--danger)" }} />
          ) : (
            <SpeakerHigh weight="duotone" size={22} style={{ color: "var(--accent)" }} />
          )}
          <div>
            <div className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
              {muted ? "Звуки выключены" : "Звуки включены"}
            </div>
            <div className="text-xs" style={{ color: "var(--text-muted)" }}>
              Полный mute. Перекрывает все ползунки ниже.
            </div>
          </div>
        </div>
        <motion.button
          type="button"
          onClick={handleMute}
          whileTap={{ scale: 0.95 }}
          aria-pressed={muted}
          aria-label={muted ? "Включить звуки" : "Выключить звуки"}
          className="rounded-lg px-3 py-1.5 text-xs font-medium transition-colors"
          style={{
            background: muted ? "var(--accent)" : "var(--input-bg)",
            color: muted ? "white" : "var(--text-primary)",
            border: `1px solid ${muted ? "var(--accent)" : "var(--border-color)"}`,
          }}
        >
          {muted ? "Включить" : "Выключить"}
        </motion.button>
      </div>

      {/* Category sliders — 2-col grid on desktop, stack on mobile. */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {CATEGORIES.map((cat) => {
          const value = valueOf(cat);
          const pct = Math.round(value * 100);
          const Icon = cat.icon;
          const disabled = muted || (cat.key !== "master" && volumes.master === 0);
          return (
            <div
              key={cat.key}
              className="glass-panel rounded-xl p-4"
              style={{ opacity: disabled ? 0.55 : 1, transition: "opacity 200ms" }}
            >
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <Icon size={18} weight="duotone" style={{ color: cat.accent }} />
                  <div>
                    <div className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
                      {cat.label}
                    </div>
                    <div className="text-[11px]" style={{ color: "var(--text-muted)" }}>
                      {cat.hint}
                    </div>
                  </div>
                </div>
                <span
                  className="text-sm font-mono tabular-nums"
                  style={{ color: cat.accent, minWidth: 34, textAlign: "right" }}
                >
                  {pct}%
                </span>
              </div>

              <Slider
                value={value}
                accent={cat.accent}
                disabled={disabled}
                onChange={(v) => {
                  handleSlide(cat, v);
                  schedulePreview(cat);
                }}
                ariaLabel={cat.label}
              />

              <div className="flex justify-between gap-2 mt-3">
                <button
                  type="button"
                  onClick={() => playSound(cat.preview)}
                  disabled={disabled}
                  className="text-xs px-2.5 py-1 rounded-lg transition-colors"
                  style={{
                    background: disabled ? "var(--input-bg)" : "var(--accent-muted)",
                    color: disabled ? "var(--text-muted)" : "var(--accent)",
                    border: "1px solid var(--border-color)",
                    cursor: disabled ? "not-allowed" : "pointer",
                  }}
                >
                  ▶ Послушать
                </button>
                <button
                  type="button"
                  onClick={() => handleSlide(cat, 0)}
                  disabled={disabled || value === 0}
                  className="text-xs px-2.5 py-1 rounded-lg transition-colors"
                  style={{
                    background: "transparent",
                    color: "var(--text-muted)",
                    border: "1px solid var(--border-color)",
                    cursor: disabled || value === 0 ? "not-allowed" : "pointer",
                  }}
                >
                  Сбросить
                </button>
              </div>
            </div>
          );
        })}
      </div>

      <p className="text-xs px-1" style={{ color: "var(--text-muted)" }}>
        Совет: Master около 70% — комфортный уровень. Если что-то слишком громкое
        — уменьшайте SFX, не Master.
      </p>
    </div>
  );
}

/* ── Tonal range slider (glass-panel themed) ──────────────────────────── */
function Slider({
  value,
  accent,
  disabled,
  onChange,
  ariaLabel,
}: {
  value: number;
  accent: string;
  disabled: boolean;
  onChange: (v: number) => void;
  ariaLabel: string;
}) {
  const pct = Math.round(value * 100);
  const sliderId = React.useId();
  return (
    <div className="relative h-5 select-none">
      {/* Track */}
      <div
        aria-hidden
        className="absolute inset-x-0 top-1/2 -translate-y-1/2 h-1.5 rounded-full"
        style={{ background: "var(--input-bg)", border: "1px solid var(--border-color)" }}
      >
        <div
          className="absolute inset-y-0 left-0 rounded-full"
          style={{
            width: `${pct}%`,
            background: accent,
            transition: "width 80ms ease-out",
            boxShadow: disabled ? "none" : `0 0 6px ${accent}`,
            opacity: disabled ? 0.4 : 1,
          }}
        />
      </div>
      {/* Visible thumb */}
      <div
        aria-hidden
        className="absolute top-1/2 rounded-full pointer-events-none"
        style={{
          left: `calc(${pct}% - 7px)`,
          transform: "translateY(-50%)",
          width: 14,
          height: 14,
          background: disabled ? "var(--text-muted)" : accent,
          border: "2px solid var(--bg-primary)",
          boxShadow: "0 1px 3px rgba(0,0,0,0.3)",
          transition: "left 80ms ease-out",
        }}
      />
      {/* Native input — full width, transparent for hit-testing only */}
      <input
        id={sliderId}
        type="range"
        min={0}
        max={1}
        step={0.01}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(Number(e.target.value))}
        aria-label={ariaLabel}
        className="absolute inset-0 w-full h-full opacity-0"
        style={{ cursor: disabled ? "not-allowed" : "pointer" }}
      />
    </div>
  );
}
