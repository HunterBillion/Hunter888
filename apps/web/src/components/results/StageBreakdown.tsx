"use client";

import { motion } from "framer-motion";
import { Check, X, ArrowRight } from "lucide-react";
import { Warning, PhoneDisconnect, Lightbulb } from "@phosphor-icons/react";

/** Stage labels matching backend STAGE_LABELS */
const STAGE_META: Record<number, { name: string; description: string }> = {
  1: { name: "Приветствие", description: "Представиться, назвать компанию, цель звонка" },
  2: { name: "Контакт", description: "Расположить к себе, показать эмпатию" },
  3: { name: "Квалификация", description: "Узнать сумму долга, кредиторов, имущество" },
  4: { name: "Презентация", description: "Объяснить банкротство, преимущества, сроки" },
  5: { name: "Возражения", description: "Обработать сомнения клиента" },
  6: { name: "Встреча", description: "Назначить конкретный следующий шаг" },
  7: { name: "Закрытие", description: "Подвести итог, подтвердить договорённость" },
};

interface StageProgressData {
  stages_completed?: number[];
  stage_scores?: Record<string, number>;
  final_stage?: number;
  final_stage_name?: string;
  total_stages?: number;
}

interface ResultDetails {
  note?: string;
  consultation_agreed?: boolean;
  hangup_recovery_bonus?: boolean;
}

interface StageBreakdownProps {
  stageProgress: StageProgressData | undefined;
  resultDetails?: ResultDetails;
  callOutcome?: string;
  emotionTimeline?: Array<{ state: string; timestamp?: number }>;
}

/** Generate recommendations based on stage data */
function generateRecommendations(
  stageProgress: StageProgressData,
  callOutcome?: string,
): Array<{ type: "warning" | "tip" | "success"; text: string }> {
  const recs: Array<{ type: "warning" | "tip" | "success"; text: string }> = [];
  const completed = new Set(stageProgress.stages_completed || []);
  const scores = stageProgress.stage_scores || {};
  const total = stageProgress.total_stages || 7;

  // Check for skipped stages
  for (let i = 1; i <= total; i++) {
    if (!completed.has(i) && i < (stageProgress.final_stage || total)) {
      const meta = STAGE_META[i];
      if (meta) {
        recs.push({
          type: "warning",
          text: `Вы пропустили этап "${meta.name}". ${meta.description} — это важно для построения доверия.`,
        });
      }
    }
  }

  // Check for low quality stages
  for (const [stageStr, score] of Object.entries(scores)) {
    const stageNum = parseInt(stageStr);
    const meta = STAGE_META[stageNum];
    if (meta && score < 0.2 && score > 0) {
      recs.push({
        type: "tip",
        text: `Этап "${meta.name}" пройден слабо (${Math.round(score * 100)}%). Попробуйте уделить больше внимания: ${meta.description}.`,
      });
    }
  }

  // Check if greeting was too short
  const greetingScore = scores["1"] || 0;
  if (greetingScore < 0.15 && completed.has(1)) {
    recs.push({
      type: "tip",
      text: "Приветствие было очень кратким. Назовите своё имя, компанию и цель звонка — это создаёт доверие.",
    });
  }

  // Check for hangup
  if (callOutcome === "hangup") {
    const finalStage = stageProgress.final_stage || 1;
    const meta = STAGE_META[finalStage];
    recs.push({
      type: "warning",
      text: `Клиент бросил трубку на этапе "${meta?.name || "?"}" (${finalStage}/${total}). Обратите внимание на тон и тактику работы с негативом.`,
    });
  }

  // Check for successful progression
  if (completed.size >= 5) {
    recs.push({
      type: "success",
      text: `Отлично! Вы прошли ${completed.size} из ${total} этапов скрипта.`,
    });
  }

  // Qualification check
  const qualScore = scores["3"] || 0;
  if (qualScore >= 0.5) {
    recs.push({
      type: "success",
      text: "Хорошая квалификация — вы задали достаточно вопросов о ситуации клиента.",
    });
  }

  return recs;
}

export default function StageBreakdown({
  stageProgress,
  resultDetails,
  callOutcome,
  emotionTimeline,
}: StageBreakdownProps) {
  if (!stageProgress) return null;

  const completed = new Set(stageProgress.stages_completed || []);
  const scores = stageProgress.stage_scores || {};
  const totalStages = stageProgress.total_stages || 7;
  const finalStage = stageProgress.final_stage || 1;
  const isHangup = callOutcome === "hangup";
  const recommendations = generateRecommendations(stageProgress, callOutcome);

  // Find hangup moment in timeline (last entry with state "hangup")
  const hangupMoment = emotionTimeline?.findIndex((e) => e.state === "hangup");

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-panel rounded-2xl p-6 md:p-8"
    >
      <h2
        className="font-display text-lg tracking-widest flex items-center gap-2 border-b pb-3 mb-6"
        style={{ color: "var(--text-primary)", borderColor: "var(--border-color)" }}
      >
        <ArrowRight size={18} style={{ color: "var(--accent)" }} />
        ЭТАПЫ СКРИПТА
      </h2>

      {/* Stage timeline */}
      <div className="space-y-2">
        {Array.from({ length: totalStages }, (_, i) => i + 1).map((num) => {
          const meta = STAGE_META[num] || { name: `Этап ${num}`, description: "" };
          const isCompleted = completed.has(num);
          const score = scores[String(num)] ?? null;
          const isSkipped = !isCompleted && num < finalStage;
          const isCurrent = num === finalStage && !isCompleted;
          const isHangupStage = isHangup && num === finalStage;

          // Score color
          let scorePct = score !== null ? Math.round(score * 100) : null;
          let scoreColor = "var(--text-muted)";
          if (scorePct !== null) {
            if (scorePct >= 50) scoreColor = "var(--success)";
            else if (scorePct >= 20) scoreColor = "var(--warning)";
            else scoreColor = "var(--danger)";
          }

          return (
            <motion.div
              key={num}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: num * 0.05 }}
              className="flex items-center gap-3 rounded-xl px-4 py-3"
              style={{
                background: isHangupStage
                  ? "rgba(229,72,77,0.08)"
                  : isSkipped
                    ? "rgba(255,165,0,0.05)"
                    : isCompleted
                      ? "rgba(61,220,132,0.04)"
                      : "rgba(255,255,255,0.02)",
                border: `1px solid ${
                  isHangupStage
                    ? "rgba(229,72,77,0.2)"
                    : isSkipped
                      ? "rgba(255,165,0,0.15)"
                      : "rgba(255,255,255,0.06)"
                }`,
              }}
            >
              {/* Status icon */}
              <div className="flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center"
                style={{
                  background: isHangupStage
                    ? "rgba(229,72,77,0.15)"
                    : isCompleted
                      ? "rgba(61,220,132,0.12)"
                      : isSkipped
                        ? "rgba(255,165,0,0.12)"
                        : "rgba(255,255,255,0.05)",
                }}
              >
                {isHangupStage ? (
                  <PhoneDisconnect size={12} weight="duotone" style={{ color: "var(--danger)" }} />
                ) : isCompleted ? (
                  <Check size={12} style={{ color: "var(--success)" }} strokeWidth={3} />
                ) : isSkipped ? (
                  <X size={12} style={{ color: "var(--warning)" }} strokeWidth={2} />
                ) : (
                  <span className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>{num}</span>
                )}
              </div>

              {/* Stage info */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span
                    className="text-sm font-medium"
                    style={{
                      color: isHangupStage ? "var(--danger)" : isSkipped ? "var(--warning)" : "var(--text-primary)",
                    }}
                  >
                    {meta.name}
                  </span>
                  {isSkipped && (
                    <span className="text-xs font-mono px-1.5 py-0.5 rounded" style={{ background: "rgba(255,165,0,0.12)", color: "var(--warning)" }}>
                      ПРОПУЩЕН
                    </span>
                  )}
                  {isHangupStage && (
                    <span className="text-xs font-mono px-1.5 py-0.5 rounded" style={{ background: "rgba(229,72,77,0.12)", color: "var(--danger)" }}>
                      HANGUP
                    </span>
                  )}
                </div>
                <p className="text-xs truncate" style={{ color: "var(--text-muted)" }}>
                  {meta.description}
                </p>
              </div>

              {/* Score bar */}
              {scorePct !== null && (
                <div className="flex-shrink-0 w-20 flex items-center gap-2">
                  <div className="flex-1 h-1.5 rounded-full overflow-hidden" style={{ background: "var(--input-bg)" }}>
                    <div
                      className="h-full rounded-full transition-all duration-500"
                      style={{ width: `${scorePct}%`, background: scoreColor }}
                    />
                  </div>
                  <span className="text-xs font-mono w-8 text-right" style={{ color: scoreColor }}>
                    {scorePct}%
                  </span>
                </div>
              )}
            </motion.div>
          );
        })}
      </div>

      {/* Summary */}
      <div className="mt-4 flex items-center gap-4 text-xs font-mono" style={{ color: "var(--text-muted)" }}>
        <span>Пройдено: <strong style={{ color: "var(--text-primary)" }}>{completed.size}/{totalStages}</strong></span>
        <span>Финальный этап: <strong style={{ color: "var(--text-primary)" }}>{STAGE_META[finalStage]?.name || `#${finalStage}`}</strong></span>
        {isHangup && (
          <span style={{ color: "var(--danger)" }}>
            <PhoneDisconnect size={11} weight="duotone" className="inline mr-1" />
            Клиент бросил трубку
          </span>
        )}
      </div>

      {/* Recommendations */}
      {recommendations.length > 0 && (
        <div className="mt-6 border-t pt-4" style={{ borderColor: "var(--border-color)" }}>
          <h3 className="font-mono text-xs uppercase tracking-widest mb-3 flex items-center gap-1.5" style={{ color: "var(--text-muted)" }}>
            <Lightbulb size={12} weight="duotone" style={{ color: "var(--warning)" }} />
            РЕКОМЕНДАЦИИ ПО СКРИПТУ
          </h3>
          <div className="space-y-2">
            {recommendations.map((rec, i) => (
              <div
                key={i}
                className="flex items-start gap-2.5 rounded-lg px-3 py-2 text-xs"
                style={{
                  background: rec.type === "success"
                    ? "rgba(61,220,132,0.05)"
                    : rec.type === "warning"
                      ? "rgba(229,72,77,0.05)"
                      : "rgba(212,168,75,0.05)",
                  border: `1px solid ${
                    rec.type === "success"
                      ? "rgba(61,220,132,0.15)"
                      : rec.type === "warning"
                        ? "rgba(229,72,77,0.15)"
                        : "rgba(212,168,75,0.15)"
                  }`,
                }}
              >
                {rec.type === "success" ? (
                  <Check size={14} className="flex-shrink-0 mt-0.5" style={{ color: "var(--success)" }} />
                ) : rec.type === "warning" ? (
                  <Warning size={14} weight="duotone" className="flex-shrink-0 mt-0.5" style={{ color: "var(--danger)" }} />
                ) : (
                  <Lightbulb size={14} weight="duotone" className="flex-shrink-0 mt-0.5" style={{ color: "var(--warning)" }} />
                )}
                <span style={{ color: "var(--text-secondary)" }}>{rec.text}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </motion.div>
  );
}
