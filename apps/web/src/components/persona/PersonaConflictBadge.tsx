"use client";

/**
 * PersonaConflictBadge — TZ-4 §9.3 / §13.4.1 inline warning chip.
 *
 * Renders a small "идентичность под вопросом" pill when the runtime
 * has detected a persona conflict in the current session. The chip
 * is intentionally low-cost visually — warn-only mode (D5 default)
 * means we shouldn't be loud here, but the manager needs to know that
 * the AI tried to drift mid-call.
 *
 * Wiring (planned):
 *   * The session-detail page subscribes to the WS event
 *     ``persona.conflict_detected`` and bumps a counter via
 *     ``onConflictDetected(payload)``.
 *   * The pre-call screen (``apps/web/src/app/training/[id]/call/page.tsx``)
 *     and ``ClientCard`` pass the latest counter into this component.
 *
 * For D6 the badge ships as a pure presentation component — no live
 * subscription yet, so consumers can pre-flight the UI shape and the
 * D7 cutover wires the actual event source.
 */

import { ShieldAlert } from "lucide-react";
import { motion } from "framer-motion";

interface PersonaConflictBadgeProps {
  /** Number of `persona.conflict_detected` events observed in this
   * context (session, client card view, etc.). When zero the badge is
   * not rendered at all — silence is the happy path. */
  count: number;
  /** Optional snapshot of the last attempted-mutation field, lifted
   * from the most recent event payload. Surfaces in the title tooltip
   * so the manager can see what the AI tried to switch ("full_name",
   * "address_form", etc.) without opening the admin event log. */
  lastAttemptedField?: string | null;
  /** Compact mode — used inside ClientCard / Timeline rows where
   * vertical space is precious. Default `false` shows the verbose
   * label "Идентичность: попытки изменения N". */
  compact?: boolean;
  /** Optional click handler — opens an audit drawer when supplied. */
  onClick?: () => void;
}

export function PersonaConflictBadge({
  count,
  lastAttemptedField,
  compact = false,
  onClick,
}: PersonaConflictBadgeProps) {
  if (!count || count <= 0) return null;

  const title = lastAttemptedField
    ? `${count} попытк${count === 1 ? "а" : count < 5 ? "и" : ""} изменить «${lastAttemptedField}» — заблокировано (TZ-4 §9.2)`
    : `${count} попыт${count === 1 ? "ка" : "ок"} изменить идентичность клиента — заблокировано (TZ-4 §9.2)`;

  const Wrapper = onClick ? motion.button : motion.span;

  return (
    <Wrapper
      onClick={onClick}
      type={onClick ? "button" : undefined}
      whileTap={onClick ? { scale: 0.96 } : undefined}
      title={title}
      className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-medium"
      style={{
        background: "color-mix(in srgb, var(--warning) 14%, transparent)",
        color: "var(--warning)",
        border: "1px solid color-mix(in srgb, var(--warning) 35%, transparent)",
        cursor: onClick ? "pointer" : "default",
      }}
    >
      <ShieldAlert size={11} />
      {compact ? `×${count}` : `Конфликт идентичности · ${count}`}
    </Wrapper>
  );
}
