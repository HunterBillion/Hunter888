"use client";

/**
 * PlanChip — компактная индикация подписки в Header.
 *
 * Phase C (2026-04-20). Шо показывает:
 *   • Plan name с цветовой меткой (scout/ranger/hunter/master)
 *   • Trial countdown ("12 дн до окончания") если is_trial
 *   • Click → /pricing (либо /pricing с подсветкой текущего)
 *
 * Скрывается если:
 *   • Юзер ещё не загружен
 *   • Роль elevated (admin/rop/methodologist) — plan для них не нерв
 *
 * Owner decision (2026-04-20): "скрой" для elevated ролей.
 */

import Link from "next/link";
import { Sparkles, Crown, ShieldCheck, Flame, Clock } from "lucide-react";
import { isElevatedRole, type PlanType } from "@/hooks/useSubscription";

interface Props {
  plan: PlanType | undefined;
  isTrial?: boolean;
  trialDaysRemaining?: number;
  role?: string | null;
}

type IconComp = React.ComponentType<{ size?: number; style?: React.CSSProperties }>;

const PLAN_META: Record<PlanType, { label: string; color: string; Icon: IconComp }> = {
  scout: {
    label: "Scout",
    color: "#94a3b8",
    Icon: Sparkles,
  },
  ranger: {
    label: "Ranger",
    color: "#4ade80",
    Icon: ShieldCheck,
  },
  hunter: {
    label: "Hunter",
    color: "#a78bfa",
    Icon: Flame,
  },
  master: {
    label: "Master",
    color: "#facc15",
    Icon: Crown,
  },
};

export function PlanChip({ plan, isTrial, trialDaysRemaining, role }: Props) {
  // Hide for elevated roles (admin/rop/methodologist) — they have master
  // auto-granted, the chip would be noise.
  if (isElevatedRole(role)) return null;
  if (!plan) return null;

  const meta = PLAN_META[plan] ?? PLAN_META.scout;
  const Icon = meta.Icon;

  return (
    <Link
      href="/billing"
      className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wider transition-all hover:scale-[1.02] whitespace-nowrap shrink-0"
      style={{
        background: `${meta.color}18`,
        color: meta.color,
        border: `1px solid ${meta.color}44`,
      }}
      aria-label={`Текущий план: ${meta.label}. Управлять подпиской`}
      title={
        isTrial
          ? `Триал ${trialDaysRemaining ?? 0} дн. Открыть подписку`
          : `План ${meta.label}. Открыть подписку`
      }
    >
      <Icon size={12} />
      <span>{meta.label}</span>
      {isTrial && typeof trialDaysRemaining === "number" && trialDaysRemaining > 0 && (
        <span
          className="inline-flex items-center gap-0.5 font-mono"
          style={{ color: meta.color, opacity: 0.85 }}
        >
          <Clock size={10} />
          {trialDaysRemaining}д
        </span>
      )}
    </Link>
  );
}
