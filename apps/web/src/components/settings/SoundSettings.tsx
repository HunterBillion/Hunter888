"use client";

/**
 * SoundSettings — карточка управления звуком на странице /settings.
 *
 * 2026-05-01 (Фаза 8):
 *   - 4 ползунка: Master / SFX / Ambient / UI (0..100)
 *   - Mute-toggle (полностью отключает все звуки)
 *   - Preview-кнопки: тестовый звук категории, чтобы юзер слышал что меняет
 *   - Все значения — в localStorage, синхронизируются между табами через
 *     useSyncExternalStore + custom event "vh-volume-change".
 *
 * Дизайн карточки повторяет существующий .glass-panel формат страницы
 * настроек, но pixel-slider кастомный — `<input type="range">` с
 * прокачанной CSS-стилизацией под пиксельную эстетику арены.
 */

import * as React from "react";
import { motion } from "framer-motion";
import { SpeakerHigh, SpeakerSimpleSlash, Headphones, GameController, Bell } from "@phosphor-icons/react";
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
  color: string;
}

const CATEGORIES: CategorySpec[] = [
  {
    key: "master",
    label: "Общая громкость",
    hint: "Базовый уровень всех звуков",
    icon: SpeakerHigh,
    preview: "ko",
    color: "var(--accent)",
  },
  {
    key: "sfx",
    label: "Эффекты боя",
    hint: "Удары, KO, fanfare, heartbeat",
    icon: GameController,
    preview: "hit",
    color: "var(--danger)",
  },
  {
    key: "ambient",
    label: "Фон арены",
    hint: "Гул и атмосфера сцены",
    icon: Headphones,
    preview: "challenge",
    color: "var(--magenta)",
  },
  {
    key: "ui",
    label: "Интерфейс",
    hint: "Клики, уведомления, переключения",
    icon: Bell,
    preview: "notification",
    color: "var(--info)",
  },
];

export function SoundSettings() {
  const volumes = useVolumes();
  const { playSound } = useSound();
  const [muted, setMuted] = React.useState<boolean>(false);
  // Sync mute on mount + listen for storage changes
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
      // un-muting — give a soft confirmation tone
      window.setTimeout(() => playSound("notification"), 50);
    }
  };

  const handleSlide = (cat: CategorySpec, value: number) => {
    if (cat.key === "master") setMasterVolume(value);
    else setCategoryVolume(cat.key, value);
  };

  // Debounced preview — играем превью через 220ms после последнего изменения,
  // чтобы не спамить звуками во время drag.
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
    <div className="space-y-4">
      {/* Master mute toggle */}
      <div
        className="flex items-center justify-between p-4"
        style={{
          background: "var(--bg-panel)",
          outline: `2px solid ${muted ? "var(--danger)" : "var(--accent)"}`,
          outlineOffset: -2,
          boxShadow: `3px 3px 0 0 ${muted ? "var(--danger)" : "var(--accent)"}`,
          borderRadius: 0,
        }}
      >
        <div className="flex items-center gap-3">
          {muted ? (
            <SpeakerSimpleSlash weight="duotone" size={24} style={{ color: "var(--danger)" }} />
          ) : (
            <SpeakerHigh weight="duotone" size={24} style={{ color: "var(--accent)" }} />
          )}
          <div>
            <div
              className="font-pixel"
              style={{
                color: "var(--text-primary)",
                fontSize: 14,
                letterSpacing: "0.16em",
                textTransform: "uppercase",
              }}
            >
              {muted ? "Звуки выключены" : "Звуки включены"}
            </div>
            <div className="text-xs" style={{ color: "var(--text-muted)" }}>
              Полный mute. Перекрывает все ползунки ниже.
            </div>
          </div>
        </div>
        <motion.button
          onClick={handleMute}
          whileHover={{ x: -1, y: -1 }}
          whileTap={{ x: 2, y: 2 }}
          className="font-pixel"
          aria-pressed={muted}
          aria-label={muted ? "Включить звуки" : "Выключить звуки"}
          style={{
            padding: "8px 16px",
            background: muted ? "var(--accent)" : "var(--bg-secondary)",
            color: muted ? "#fff" : "var(--text-primary)",
            border: `2px solid ${muted ? "var(--accent)" : "var(--border-color)"}`,
            borderRadius: 0,
            fontSize: 12,
            letterSpacing: "0.18em",
            textTransform: "uppercase",
            boxShadow: muted
              ? "3px 3px 0 0 #000, 0 0 12px var(--accent-glow)"
              : "2px 2px 0 0 var(--border-color)",
            cursor: "pointer",
          }}
        >
          {muted ? "Включить" : "Mute"}
        </motion.button>
      </div>

      {/* Volume sliders */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {CATEGORIES.map((cat) => {
          const value = valueOf(cat);
          const pct = Math.round(value * 100);
          const Icon = cat.icon;
          const disabled = muted || (cat.key !== "master" && volumes.master === 0);
          return (
            <div
              key={cat.key}
              className="p-4"
              style={{
                background: "var(--bg-panel)",
                outline: `2px solid ${disabled ? "var(--border-color)" : cat.color}`,
                outlineOffset: -2,
                boxShadow: disabled
                  ? "2px 2px 0 0 var(--border-color)"
                  : `3px 3px 0 0 ${cat.color}`,
                borderRadius: 0,
                opacity: disabled ? 0.55 : 1,
                transition: "opacity 200ms",
              }}
            >
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <Icon size={18} weight="duotone" style={{ color: cat.color }} />
                  <div>
                    <div
                      className="font-pixel"
                      style={{
                        color: "var(--text-primary)",
                        fontSize: 13,
                        letterSpacing: "0.14em",
                        textTransform: "uppercase",
                        lineHeight: 1.1,
                      }}
                    >
                      {cat.label}
                    </div>
                    <div
                      className="text-[11px] mt-0.5"
                      style={{ color: "var(--text-muted)" }}
                    >
                      {cat.hint}
                    </div>
                  </div>
                </div>
                <span
                  className="font-pixel tabular-nums"
                  style={{
                    color: cat.color,
                    fontSize: 16,
                    letterSpacing: "0.04em",
                    minWidth: 38,
                    textAlign: "right",
                  }}
                >
                  {pct}
                </span>
              </div>

              <PixelSlider
                value={value}
                color={cat.color}
                disabled={disabled}
                onChange={(v) => {
                  handleSlide(cat, v);
                  schedulePreview(cat);
                }}
                ariaLabel={cat.label}
              />

              <div className="flex justify-between mt-2">
                <button
                  type="button"
                  onClick={() => playSound(cat.preview)}
                  disabled={disabled}
                  className="font-pixel"
                  style={{
                    padding: "4px 10px",
                    background: "transparent",
                    color: disabled ? "var(--text-muted)" : cat.color,
                    border: `1px solid ${disabled ? "var(--border-color)" : cat.color}`,
                    borderRadius: 0,
                    fontSize: 10,
                    letterSpacing: "0.18em",
                    textTransform: "uppercase",
                    cursor: disabled ? "not-allowed" : "pointer",
                  }}
                >
                  ▶ Послушать
                </button>
                <button
                  type="button"
                  onClick={() => handleSlide(cat, 0)}
                  disabled={disabled || value === 0}
                  className="font-pixel"
                  style={{
                    padding: "4px 10px",
                    background: "transparent",
                    color: "var(--text-muted)",
                    border: "1px solid var(--border-color)",
                    borderRadius: 0,
                    fontSize: 10,
                    letterSpacing: "0.18em",
                    textTransform: "uppercase",
                    cursor: disabled || value === 0 ? "not-allowed" : "pointer",
                  }}
                >
                  ↺ 0
                </button>
              </div>
            </div>
          );
        })}
      </div>

      <p
        className="text-xs"
        style={{ color: "var(--text-muted)", padding: "0 4px" }}
      >
        Совет: установи Master около 70% для комфортной громкости. Если что-то
        слишком громкое — уменьшай SFX, а не Master.
      </p>
    </div>
  );
}

/* ── Pixel-styled range slider ──────────────────────────────────────── */
function PixelSlider({
  value,
  color,
  disabled,
  onChange,
  ariaLabel,
}: {
  value: number;
  color: string;
  disabled: boolean;
  onChange: (v: number) => void;
  ariaLabel: string;
}) {
  const pct = Math.round(value * 100);
  const sliderId = React.useId();
  return (
    <div className="relative" style={{ height: 22 }}>
      {/* Track */}
      <div
        aria-hidden
        className="absolute"
        style={{
          left: 0,
          right: 0,
          top: 7,
          height: 8,
          background: "var(--bg-secondary)",
          outline: "2px solid var(--text-primary)",
          outlineOffset: -2,
          boxShadow: "2px 2px 0 0 #000",
        }}
      >
        {/* Fill */}
        <div
          style={{
            position: "absolute",
            left: 0,
            top: 0,
            bottom: 0,
            width: `${pct}%`,
            background: color,
            transition: "width 80ms ease-out, background 200ms",
            boxShadow: disabled ? "none" : `0 0 6px ${color}`,
          }}
        />
      </div>
      {/* Native input — на полную ширину, transparent thumb управляет позицией */}
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
      {/* Pixel thumb (visual) */}
      {!disabled && (
        <div
          aria-hidden
          style={{
            position: "absolute",
            left: `calc(${pct}% - 7px)`,
            top: 1,
            width: 14,
            height: 20,
            background: color,
            outline: "2px solid var(--text-primary)",
            outlineOffset: -2,
            boxShadow: "2px 2px 0 0 #000",
            transition: "left 80ms ease-out",
            pointerEvents: "none",
          }}
        />
      )}
    </div>
  );
}
