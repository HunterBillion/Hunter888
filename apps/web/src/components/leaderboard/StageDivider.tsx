"use client";

/**
 * StageDivider — пиксельный разделитель между секциями /leaderboard.
 *
 * 2026-05-08 — часть аркадного редизайна. Заменяет невзрачные H1
 * предыдущей версии. Геометрия:
 *   - 2px solid bordered «лента» во всю ширину
 *   - в центре — крупный (≥ 24px desktop / 18px mobile) пиксельный
 *     заголовок: «АРЕНА I · ЛИГА» (римские цифры — пиксель-стиль)
 *   - по краям — маленькие пиксельные «звёзды» из ▰▰▰
 *   - акцентный цвет — параметр `accent`, с glow-shadow
 *
 * Кликабельный (если onClick передан) — используется в StageSelect для
 * мягкого скролла к этой секции.
 */

import type { ReactNode } from "react";

interface Props {
  /** Римская цифра — «I», «II», «III», «IV». */
  numeral: string;
  /** Имя арены. Кириллица обязательна (font-pixel поддерживает). */
  title: string;
  /** Опциональный подзаголовок справа маленьким текстом. */
  subtitle?: ReactNode;
  /** Цвет акцента — сейчас фиолетовый по дефолту, но каждая арена
   *  может иметь свой оттенок. Принимает любую CSS color value. */
  accent?: string;
  /** ID для якорной навигации (id={`stage-${id}`}). */
  id: string;
}

export function StageDivider({
  numeral,
  title,
  subtitle,
  accent = "var(--accent)",
  id,
}: Props) {
  return (
    <div
      id={`stage-${id}`}
      // 2026-05-08: scroll-margin-top, чтобы при якорном скролле секция
      // не упиралась под sticky-навигацию StageSelect (90px высота).
      className="relative mt-12 mb-6"
      style={{ scrollMarginTop: "112px" }}
    >
      {/* Левая «лента» */}
      <div
        aria-hidden
        className="absolute left-0 top-1/2 -translate-y-1/2 h-[2px]"
        style={{
          right: "calc(50% + 200px)",
          background: `linear-gradient(to right, transparent 0%, ${accent} 100%)`,
          boxShadow: `0 0 10px ${accent}`,
        }}
      />

      {/* Правая «лента» */}
      <div
        aria-hidden
        className="absolute right-0 top-1/2 -translate-y-1/2 h-[2px]"
        style={{
          left: "calc(50% + 200px)",
          background: `linear-gradient(to left, transparent 0%, ${accent} 100%)`,
          boxShadow: `0 0 10px ${accent}`,
        }}
      />

      {/* Центральный блок */}
      <div className="flex justify-center">
        <div
          className="font-pixel uppercase tracking-[0.18em] flex items-center gap-3 px-4 md:px-6 py-2 rounded-sm"
          style={{
            color: accent,
            background: "rgba(8, 5, 18, 0.85)",
            border: `2px solid ${accent}`,
            boxShadow: `0 0 18px ${accent}55, inset 0 0 8px ${accent}22`,
            // 2026-05-08: минимум 18px — пользователь явно попросил «везде ≥14px»,
            // у заголовков-разделителей берём с запасом для иерархии.
            fontSize: "clamp(20px, 3vw, 28px)",
            lineHeight: 1.05,
          }}
        >
          <span aria-hidden style={{ opacity: 0.6 }}>▰▰▰</span>
          <span>
            АРЕНА {numeral} · {title}
          </span>
          <span aria-hidden style={{ opacity: 0.6 }}>▰▰▰</span>
        </div>
      </div>

      {/* Subtitle (по центру под заголовком) */}
      {subtitle && (
        <div
          className="text-center mt-3 font-pixel uppercase tracking-widest"
          style={{
            color: "var(--text-muted)",
            // 14px — нижняя граница из требований пользователя.
            fontSize: "14px",
          }}
        >
          {subtitle}
        </div>
      )}
    </div>
  );
}
