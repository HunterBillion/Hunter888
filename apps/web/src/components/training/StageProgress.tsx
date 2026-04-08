"use client";

import { motion, AnimatePresence } from "framer-motion";
import { Check } from "lucide-react";

/** Labels for 7-step BFL sales script stages. */
const STAGE_LABELS: Record<number, { short: string; full: string; hint: string }> = {
  1: { short: "Привет.", full: "Приветствие", hint: "Представьтесь, назовите компанию и цель звонка" },
  2: { short: "Контакт", full: "Контакт", hint: "Установите раппорт, узнайте имя, создайте комфорт" },
  3: { short: "Квалиф.", full: "Квалификация", hint: "Выясните ситуацию: долг, кредиторы, имущество" },
  4: { short: "Презент.", full: "Презентация", hint: "Представьте услугу банкротства и преимущества" },
  5: { short: "Возраж.", full: "Возражения", hint: "Обработайте сомнения о цене, доверии, сроках" },
  6: { short: "Встреча", full: "Встреча", hint: "Назначьте консультацию, согласуйте время и место" },
  7: { short: "Закр.", full: "Закрытие", hint: "Подтвердите договорённости и следующий шаг" },
};

interface StageProgressProps {
  currentStage: number;        // 1-7
  stagesCompleted: number[];   // e.g. [1, 2]
  totalStages: number;         // 7
}

export default function StageProgressBar({
  currentStage,
  stagesCompleted,
  totalStages,
}: StageProgressProps) {
  const stages = Array.from({ length: totalStages }, (_, i) => i + 1);
  const completedSet = new Set(stagesCompleted);
  const progressPct = (stagesCompleted.length / totalStages) * 100;

  return (
    <div className="flex flex-col">
      <div
        className="text-sm font-semibold mb-3"
        style={{ color: "var(--text-secondary)" }}
      >
        Этапы скрипта
      </div>

      {/* Progress bar */}
      <div className="h-1 rounded-full overflow-hidden mb-3" style={{ background: "var(--input-bg)" }}>
        <motion.div
          className="h-full rounded-full"
          style={{
            background: "linear-gradient(90deg, var(--success), var(--accent))",
            boxShadow: "0 0 6px rgba(0,255,148,0.3)",
          }}
          animate={{ width: `${progressPct}%` }}
          transition={{ duration: 0.6, ease: "easeOut" }}
        />
      </div>

      {/* Stage circles — desktop */}
      <div className="hidden sm:flex items-center">
        {stages.map((num, idx) => {
          const isCompleted = completedSet.has(num);
          const isCurrent = num === currentStage && !isCompleted;
          const label = STAGE_LABELS[num] || { short: `${num}`, full: `Этап ${num}`, hint: "" };

          // Connector line before this circle (not before first)
          const prevCompleted = idx > 0 && completedSet.has(stages[idx - 1]);

          return (
            <div key={num} className="contents">
              {/* Connector line */}
              {idx > 0 && (
                <div
                  className="flex-1 h-px"
                  style={{
                    background: prevCompleted
                      ? "var(--success, #00FF94)"
                      : "var(--border-color)",
                  }}
                />
              )}

              {/* Circle with tooltip */}
              <div className="relative group flex-shrink-0">
                <AnimatePresence mode="wait">
                  {isCompleted ? (
                    <motion.div
                      key="done"
                      initial={{ scale: 0 }}
                      animate={{ scale: 1 }}
                      transition={{ type: "spring", stiffness: 500, damping: 20 }}
                      className="flex items-center justify-center w-6 h-6 rounded-full"
                      style={{
                        background: "rgba(0,255,148,0.15)",
                        border: "1.5px solid var(--success, #00FF94)",
                      }}
                    >
                      <Check size={12} style={{ color: "#fff" }} strokeWidth={3} />
                    </motion.div>
                  ) : isCurrent ? (
                    <motion.div
                      key="current"
                      animate={{
                        boxShadow: [
                          "0 0 0px rgba(99,102,241,0.3)",
                          "0 0 10px rgba(99,102,241,0.6)",
                          "0 0 0px rgba(99,102,241,0.3)",
                        ],
                      }}
                      transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
                      className="flex items-center justify-center w-6 h-6 rounded-full"
                      style={{
                        background: "rgba(99,102,241,0.15)",
                        border: "1.5px solid var(--accent)",
                      }}
                    >
                      <span
                        className="text-xs font-bold"
                        style={{ color: "var(--accent)" }}
                      >
                        {num}
                      </span>
                    </motion.div>
                  ) : (
                    <motion.div
                      key="pending"
                      className="flex items-center justify-center w-6 h-6 rounded-full"
                      style={{
                        background: "transparent",
                        border: "1.5px solid var(--border-color)",
                      }}
                    >
                      <span
                        className="text-xs font-bold"
                        style={{ color: "var(--text-muted)" }}
                      >
                        {num}
                      </span>
                    </motion.div>
                  )}
                </AnimatePresence>

                {/* Tooltip */}
                <div
                  className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-2.5 py-1.5 rounded-lg text-xs opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-20 w-40 text-center"
                  style={{
                    background: "var(--surface, #1a1a2e)",
                    border: "1px solid var(--border-color)",
                    color: "var(--text-secondary)",
                    boxShadow: "0 4px 16px rgba(0,0,0,0.3)",
                  }}
                >
                  <div className="font-semibold mb-0.5" style={{ color: "var(--text-primary)" }}>
                    {label.full}
                    {isCompleted && " \u2714"}
                    {isCurrent && " \u25cf"}
                  </div>
                  <div className="leading-relaxed" style={{ color: "var(--text-muted)" }}>
                    {label.hint}
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Stage dots — mobile (compact) */}
      <div className="flex sm:hidden items-center justify-center gap-1.5">
        {stages.map((num) => {
          const isCompleted = completedSet.has(num);
          const isCurrent = num === currentStage && !isCompleted;

          return (
            <motion.div
              key={num}
              className="rounded-full"
              style={{
                width: isCurrent ? 12 : 6,
                height: 6,
                background: isCompleted
                  ? "var(--success, #00FF94)"
                  : isCurrent
                    ? "var(--accent)"
                    : "var(--border-color)",
              }}
              animate={isCurrent ? { opacity: [0.5, 1, 0.5] } : {}}
              transition={isCurrent ? { duration: 1.5, repeat: Infinity } : {}}
              layout
            />
          );
        })}
        <span
          className="ml-2 text-xs"
          style={{ color: "var(--text-muted)" }}
        >
          {stagesCompleted.length}/{totalStages}
        </span>
      </div>
    </div>
  );
}
