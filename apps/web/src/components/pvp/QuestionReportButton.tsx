"use client";

/**
 * QuestionReportButton — «Сообщить о проблеме» в панели вариантов
 * квиза (PR-12, 2026-05-07).
 *
 * Дублирует ReportAnswerButton из verdict-bubble, но живёт прямо в
 * левой панели рядом с ПОДСКАЗКА. Привязка к ПОСЛЕДНЕМУ answer'у
 * с answerId — таким образом юзер может пожаловаться, не возвращаясь
 * глазами в чат-историю.
 *
 * Поведение:
 *   - lastAnswerId === undefined  → кнопка disabled с тултипом «Сначала
 *     ответь на вопрос — потом можно пожаловаться на оценку».
 *   - lastAnswerId есть          → клик открывает ту же модалку, что
 *     ReportAnswerButton.
 */

import { ReportAnswerButton } from "./ReportAnswerButton";
import { Flag } from "lucide-react";

interface Props {
  lastAnswerId?: string;
}

export function QuestionReportButton({ lastAnswerId }: Props) {
  if (lastAnswerId) {
    // Reuse the per-answer button with full-width styling for the panel
    // location. Wrapping div forces the inline-flex pixel chip to
    // stretch and match the ПОДСКАЗКА button width.
    return (
      <div className="mt-2 [&>button]:w-full [&>button]:justify-center [&>button]:py-3">
        <ReportAnswerButton answerId={lastAnswerId} />
      </div>
    );
  }

  return (
    <button
      type="button"
      disabled
      title="Сначала ответь на вопрос — потом можно сообщить о проблеме с оценкой."
      className="mt-2 flex w-full items-center justify-center gap-2 py-3 px-3"
      style={{
        background: "transparent",
        color: "var(--text-muted)",
        border: "1px dashed var(--border-color)",
        borderRadius: 0,
        opacity: 0.5,
        cursor: "not-allowed",
      }}
    >
      <Flag size={14} />
      <span className="font-pixel text-[12px] uppercase tracking-widest">
        Сообщить о проблеме
      </span>
    </button>
  );
}
