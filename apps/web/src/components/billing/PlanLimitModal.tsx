"use client";

/**
 * PlanLimitModal — global upsell dialog triggered by 429 plan-limit events.
 *
 * Phase C (2026-04-20). Wired into AuthLayout. Listens for the
 * `plan-limit-reached` CustomEvent emitted by `lib/api.ts` when a 429
 * response carries the structured payload:
 *   { feature, plan, limit, used, message }
 *
 * Shows a context-aware upsell: which feature ran out, which tier lifts
 * the limit, CTA to /pricing. Owner feedback: generic toast → proper
 * dialog so user understands "это не баг, это лимит Scout" and can act.
 */

import Link from "next/link";
import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Flame, Sparkles, Zap, BookOpen, Rocket, X } from "lucide-react";
import type { PlanType } from "@/hooks/useSubscription";

interface LimitPayload {
  feature: string;    // sessions | pvp | rag
  plan: PlanType | string;
  limit: number;
  used: number;
  message: string;
}

type IconComp = React.ComponentType<{ size?: number; style?: React.CSSProperties; className?: string }>;

const FEATURE_META: Record<
  string,
  { label: string; icon: IconComp; nextTier: string; nextBenefit: string }
> = {
  sessions: {
    label: "Тренировок в день",
    icon: Flame,
    nextTier: "Ranger",
    nextBenefit: "10 тренировок в день + AI coach",
  },
  pvp: {
    label: "PvP матчей в день",
    icon: Zap,
    nextTier: "Ranger",
    nextBenefit: "10 матчей в день. Hunter — без лимита",
  },
  rag: {
    label: "RAG-запросов в день",
    icon: BookOpen,
    nextTier: "Ranger",
    nextBenefit: "50 запросов в день. Hunter — 500",
  },
};

const PLAN_COLOR: Record<string, string> = {
  scout: "#94a3b8",
  ranger: "#4ade80",
  hunter: "#a78bfa",
  master: "#facc15",
};

export function PlanLimitModal() {
  const [payload, setPayload] = useState<LimitPayload | null>(null);

  useEffect(() => {
    const handler = (e: Event) => {
      const evt = e as CustomEvent<LimitPayload>;
      if (!evt.detail) return;
      setPayload(evt.detail);
    };
    window.addEventListener("plan-limit-reached", handler as EventListener);
    return () => {
      window.removeEventListener(
        "plan-limit-reached",
        handler as EventListener,
      );
    };
  }, []);

  const close = () => setPayload(null);

  const meta = payload ? FEATURE_META[payload.feature] : null;
  const accent = payload ? PLAN_COLOR[payload.plan] ?? "#a78bfa" : "#a78bfa";

  return (
    <AnimatePresence>
      {payload && meta && (
        <motion.div
          className="fixed inset-0 z-[120] flex items-center justify-center px-4"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.18 }}
          style={{
            background: "rgba(6,2,15,0.72)",
            backdropFilter: "blur(6px)",
          }}
          onClick={close}
          role="dialog"
          aria-modal="true"
          aria-labelledby="plan-limit-title"
        >
          <motion.div
            className="relative w-full max-w-md rounded-2xl overflow-hidden"
            onClick={(e) => e.stopPropagation()}
            initial={{ y: 24, scale: 0.96, opacity: 0 }}
            animate={{ y: 0, scale: 1, opacity: 1 }}
            exit={{ y: 12, scale: 0.98, opacity: 0 }}
            transition={{ type: "spring", stiffness: 320, damping: 26 }}
            style={{
              background:
                "linear-gradient(180deg, rgba(24,16,40,0.98), rgba(14,9,26,0.98))",
              border: `1px solid ${accent}55`,
              boxShadow: `0 40px 80px -20px ${accent}66`,
            }}
          >
            <button
              type="button"
              onClick={close}
              className="absolute top-3 right-3 rounded-lg p-1.5 transition-colors hover:bg-white/10"
              aria-label="Закрыть"
              style={{ color: "#c9bfee" }}
            >
              <X size={16} />
            </button>

            <div className="px-5 pt-5 pb-4">
              <div
                className="inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[10px] uppercase tracking-wider font-semibold"
                style={{
                  background: `${accent}22`,
                  color: accent,
                  border: `1px solid ${accent}44`,
                }}
              >
                <Sparkles size={10} />
                План {String(payload.plan).toUpperCase()}
              </div>
              <h2
                id="plan-limit-title"
                className="mt-2 text-xl font-bold"
                style={{ color: "#f4f1ff" }}
              >
                Дневной лимит достигнут
              </h2>
              <div
                className="mt-2 rounded-xl p-3 flex items-center gap-3"
                style={{
                  background: `${accent}12`,
                  border: `1px solid ${accent}22`,
                }}
              >
                <div
                  className="flex h-10 w-10 items-center justify-center rounded-xl"
                  style={{ background: `${accent}22`, color: accent }}
                >
                  <meta.icon size={18} />
                </div>
                <div className="flex-1 min-w-0">
                  <div
                    className="text-[11px] uppercase tracking-widest"
                    style={{ color: "#c9bfee" }}
                  >
                    {meta.label}
                  </div>
                  <div
                    className="text-lg font-mono font-bold tabular-nums"
                    style={{ color: "#f4f1ff" }}
                  >
                    {payload.used} / {payload.limit}
                  </div>
                </div>
              </div>
            </div>

            <div
              className="px-5 py-4 border-t"
              style={{ borderColor: `${accent}22` }}
            >
              <div
                className="text-[11px] uppercase tracking-wider font-semibold mb-1"
                style={{ color: accent }}
              >
                <Rocket size={11} className="inline mr-1 -mt-0.5" />
                Следующий шаг: {meta.nextTier}
              </div>
              <p
                className="text-[13px] leading-relaxed"
                style={{ color: "#e5dfff" }}
              >
                {meta.nextBenefit}
              </p>
            </div>

            <div
              className="flex items-center justify-end gap-2 px-5 py-3"
              style={{
                background: "rgba(0,0,0,0.3)",
                borderTop: `1px solid ${accent}22`,
              }}
            >
              <button
                type="button"
                onClick={close}
                className="rounded-lg px-3 py-1.5 text-[12px] font-semibold"
                style={{
                  color: "#c9bfee",
                  background: "transparent",
                }}
              >
                Понял, завтра
              </button>
              <Link
                href="/pricing"
                onClick={close}
                className="rounded-lg px-3 py-1.5 text-[12px] font-semibold transition-all"
                style={{
                  background: accent,
                  color: "#0b0b14",
                  boxShadow: `0 12px 20px -10px ${accent}`,
                }}
              >
                Обновить план
              </Link>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
