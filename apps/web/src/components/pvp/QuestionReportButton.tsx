"use client";

/**
 * QuestionReportButton — глобальная «Сообщить о проблеме» в панели
 * вариантов квиза (и над free-text input bar).
 *
 * PR-12 (создан) → PR-14 (redesigned). Раньше: тонкая dashed-полоса
 * с маленьким текстом, disabled-tooltip только нативный (HTML title).
 * Теперь: яркая жёлтая кнопка во всю ширину с понятным текстом,
 * чёткая disabled-плашка с объяснением прямо в кнопке.
 *
 * Привязка к последнему answer'у с answerId — пользователь жалуется
 * на последний verdict AI. Если ответа ещё не было — disabled с
 * понятным текстом «Ответьте сначала».
 */

import { ReportAnswerButton } from "./ReportAnswerButton";
import { Flag } from "lucide-react";

interface Props {
  lastAnswerId?: string;
}

export function QuestionReportButton({ lastAnswerId }: Props) {
  if (lastAnswerId) {
    // PR-14: ReportAnswerButton сам по себе уже заметный (warning-yellow
    // bordered chip). Здесь просто растягиваем на всю ширину родителя
    // через CSS-селектор.
    return (
      <div className="mt-2 w-full [&>button]:w-full [&>button]:justify-center [&>button]:py-3 [&>button]:text-[12px]">
        <ReportAnswerButton answerId={lastAnswerId} />
      </div>
    );
  }

  return (
    <button
      type="button"
      disabled
      title="Жалоба будет доступна после первого ответа на вопрос"
      className="mt-2 flex w-full items-center justify-center gap-2 px-3 py-3 font-pixel uppercase text-[11px]"
      style={{
        background: "transparent",
        color: "var(--text-muted)",
        border: "1px dashed var(--border-color)",
        borderRadius: 0,
        opacity: 0.55,
        cursor: "not-allowed",
        letterSpacing: "0.14em",
      }}
    >
      <Flag size={13} />
      <span>Ответьте сначала, потом жалуйтесь</span>
    </button>
  );
}
