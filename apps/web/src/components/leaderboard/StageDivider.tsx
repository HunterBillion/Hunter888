"use client";

/**
 * StageDivider — пиксельный разделитель между секциями /leaderboard.
 *
 * 2026-05-08 — часть аркадного редизайна. Заменяет невзрачные H1.
 *
 * 2026-05-08 (полировка по фидбеку): убраны боковые «ленты»-градиенты,
 * которые упирались в центральную плашку и создавали визуальные «битые
 * полосы» (видно на скриншоте от пользователя). Теперь — чистый
 * пиксельный «бар»:
 *   - тонкая 1px пунктирная лента во всю ширину (sub-разделитель)
 *   - центральная плашка-«ярлык» с заголовком сверху ленты
 *   - subtitle под плашкой
 *
 * Никаких glow-overlap артефактов: лента проходит ПОЗАДИ плашки,
 * z-index 0, плашка z-index 1. Пиксельный, аркадный, без шума.
 */

import type { ReactNode } from "react";

interface Props {
  /** Римская цифра — «I», «II», «III», «IV». */
  numeral: string;
  /** Имя арены. Кириллица обязательна (font-pixel поддерживает). */
  title: string;
  /** Опциональный подзаголовок под плашкой. */
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
      // не упиралась под sticky-навигацию StageSelect (~112px высота).
      className="relative mt-14 mb-6"
      style={{ scrollMarginTop: "112px" }}
    >
      {/* Подложка-лента: одна тонкая пунктирная горизонталь во всю ширину.
          Идёт за плашкой, на её уровне центральной оси. Без бликов,
          без градиентов, без glow — чистый аркадный пунктир. */}
      <div
        aria-hidden
        className="absolute left-0 right-0 top-1/2 -translate-y-1/2"
        style={{
          height: 0,
          borderTop: `1px dashed ${accent}66`,
          opacity: 0.55,
          zIndex: 0,
        }}
      />

      {/* Центральная плашка с заголовком */}
      <div className="relative flex justify-center" style={{ zIndex: 1 }}>
        <div
          className="font-pixel uppercase tracking-[0.18em] flex items-center gap-3 px-5 md:px-7 py-2.5 rounded-sm"
          style={{
            color: accent,
            // Чуть плотнее фон — чтобы пунктирная лента позади визуально
            // обрывалась на границе плашки (без glow-overlap).
            background: "rgba(8, 5, 18, 0.97)",
            border: `2px solid ${accent}`,
            // Glow только наружу, мягкий — как неоновая надпись в аркадном
            // зале. Без inset — чтобы текст оставался чёткий.
            boxShadow: `0 0 14px ${accent}55, 0 0 2px ${accent}`,
            fontSize: "clamp(20px, 3vw, 28px)",
            lineHeight: 1.05,
          }}
        >
          <span aria-hidden style={{ opacity: 0.55, fontSize: "0.7em" }}>▰</span>
          <span>
            АРЕНА {numeral} · {title}
          </span>
          <span aria-hidden style={{ opacity: 0.55, fontSize: "0.7em" }}>▰</span>
        </div>
      </div>

      {/* Subtitle (по центру под плашкой) */}
      {subtitle && (
        <div
          className="text-center mt-3 font-pixel uppercase tracking-widest"
          style={{
            color: "var(--text-muted)",
            fontSize: "14px",
          }}
        >
          {subtitle}
        </div>
      )}
    </div>
  );
}
