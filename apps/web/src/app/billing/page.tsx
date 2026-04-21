"use client";

/**
 * /billing — authenticated user's subscription panel.
 *
 * Shows: current plan (Scout/Ranger/Hunter/Master), trial countdown,
 * today's usage bars (sessions/PvP/RAG), feature matrix (what's included),
 * and an Upgrade button that routes to /pricing (the marketing page).
 *
 * Why separate from /pricing:
 *   /pricing is in (landing) — for anonymous visitors, uses useLandingAuth,
 *   CTAs push to /register. Authenticated users clicking "Подписка" in the
 *   header used to land on this visitor-flow page, which redirected them to
 *   /login (the auth context didn't match). /billing fills that gap.
 */

import Link from "next/link";
import { motion } from "framer-motion";
import {
  Crown, Sparkles, Star, Medal, Clock, Infinity as InfinityIcon,
  Check, X, ArrowRight, TrendingUp, Zap,
} from "lucide-react";
import AuthLayout from "@/components/layout/AuthLayout";
import { useSubscription, type PlanType } from "@/hooks/useSubscription";

// ── Plan metadata — display labels and brand color per tier ──────
const PLAN_META: Record<PlanType, {
  label: string;
  name: string;
  color: string;
  Icon: typeof Star;
  tagline: string;
}> = {
  scout: { label: "Scout", name: "Бесплатный", color: "#9ca3af", Icon: Star,
    tagline: "Старт охоты. 3 сессии в день." },
  ranger: { label: "Ranger", name: "Базовый", color: "#60a5fa", Icon: Sparkles,
    tagline: "Для активных. 15 сессий, AI-коуч." },
  hunter: { label: "Hunter", name: "Pro", color: "#a78bfa", Icon: Medal,
    tagline: "Безлимит + все 12 глав + экспорт." },
  master: { label: "Master", name: "Enterprise", color: "#fbbf24", Icon: Crown,
    tagline: "Команда + API + SLA + voice cloning." },
};

// ── Usage bar — visual progress indicator ────────────────────────
function UsageBar({ used, limit, label, icon: Icon }: {
  used: number;
  limit: number;
  label: string;
  icon: typeof TrendingUp;
}) {
  const unlimited = limit < 0;
  const pct = unlimited ? 0 : Math.min(100, (used / Math.max(limit, 1)) * 100);
  const atLimit = !unlimited && used >= limit;
  const color = atLimit ? "var(--error, #f87171)" : pct > 80 ? "#fbbf24" : "var(--accent)";

  return (
    <div className="rounded-xl p-4" style={{ background: "var(--input-bg)", border: "1px solid var(--border-color)" }}>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <Icon size={16} style={{ color: "var(--text-muted)" }} />
          <span className="text-sm font-medium" style={{ color: "var(--text-secondary)" }}>{label}</span>
        </div>
        <div className="text-sm font-mono tabular-nums" style={{ color: atLimit ? color : "var(--text-primary)" }}>
          {unlimited ? (
            <span className="inline-flex items-center gap-1"><InfinityIcon size={14} /> без лимита</span>
          ) : (
            <>{used} <span style={{ color: "var(--text-muted)" }}>/ {limit}</span></>
          )}
        </div>
      </div>
      {!unlimited && (
        <div className="h-1.5 rounded-full overflow-hidden" style={{ background: "var(--border-color)" }}>
          <motion.div
            className="h-full rounded-full"
            initial={{ width: 0 }}
            animate={{ width: `${pct}%` }}
            transition={{ duration: 0.5, ease: "easeOut" }}
            style={{ background: color }}
          />
        </div>
      )}
      {atLimit && (
        <p className="text-xs mt-2" style={{ color }}>
          Лимит исчерпан. Обнови план для продолжения.
        </p>
      )}
    </div>
  );
}

// ── Feature row — yes/no table ───────────────────────────────────
function FeatureRow({ label, enabled, detail }: { label: string; enabled: boolean; detail?: string }) {
  return (
    <div
      className="flex items-center justify-between py-3 px-4 rounded-lg"
      style={{ background: enabled ? "color-mix(in oklab, var(--accent-muted) 40%, transparent)" : "transparent" }}
    >
      <div>
        <div className="text-sm" style={{ color: enabled ? "var(--text-primary)" : "var(--text-muted)" }}>{label}</div>
        {detail && <div className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>{detail}</div>}
      </div>
      {enabled ? (
        <Check size={18} style={{ color: "var(--accent)" }} />
      ) : (
        <X size={18} style={{ color: "var(--text-muted)", opacity: 0.5 }} />
      )}
    </div>
  );
}

export default function BillingPage() {
  const { data, loading, error } = useSubscription();

  if (loading) {
    return (
      <AuthLayout>
        <div className="app-page flex items-center justify-center min-h-[60vh]">
          <div className="text-sm" style={{ color: "var(--text-muted)" }}>Загружаем данные подписки…</div>
        </div>
      </AuthLayout>
    );
  }

  if (!data || error) {
    return (
      <AuthLayout>
        <div className="app-page flex items-center justify-center min-h-[60vh]">
          <div className="glass-panel p-8 text-center max-w-md">
            <h2 className="text-xl font-bold mb-2" style={{ color: "var(--text-primary)" }}>Не удалось загрузить подписку</h2>
            <p className="text-sm mb-4" style={{ color: "var(--text-muted)" }}>{error || "Повторите попытку позже"}</p>
            <Link href="/home" className="text-sm" style={{ color: "var(--accent)" }}>Вернуться на главную →</Link>
          </div>
        </div>
      </AuthLayout>
    );
  }

  const meta = PLAN_META[data.plan] ?? PLAN_META.scout;
  const Icon = meta.Icon;
  const isTrial = data.is_trial;
  const isScout = data.plan === "scout";
  const isMaster = data.plan === "master";

  return (
    <AuthLayout>
      <div className="app-page max-w-4xl mx-auto space-y-6">
        {/* ── HEADER — Plan summary card ────────────────────────── */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          className="glass-panel p-6 sm:p-8 relative overflow-hidden"
          style={{ borderColor: `${meta.color}55`, borderWidth: 2 }}
        >
          {/* Accent glow — tinted by plan color */}
          <div
            className="absolute -top-16 -right-16 w-64 h-64 rounded-full pointer-events-none opacity-20"
            style={{ background: `radial-gradient(circle, ${meta.color} 0%, transparent 60%)` }}
          />

          <div className="relative flex items-start justify-between gap-4 flex-wrap">
            <div className="min-w-0">
              <div className="flex items-center gap-2 mb-2">
                <div
                  className="flex items-center justify-center w-10 h-10 rounded-lg"
                  style={{ background: `${meta.color}22`, border: `1px solid ${meta.color}44` }}
                >
                  <Icon size={20} style={{ color: meta.color }} />
                </div>
                <div>
                  <div className="text-xs uppercase tracking-widest font-mono" style={{ color: "var(--text-muted)" }}>Ваш план</div>
                  <div className="text-2xl font-display font-bold" style={{ color: meta.color }}>
                    {meta.label} <span className="text-base font-normal" style={{ color: "var(--text-secondary)" }}>· {meta.name}</span>
                  </div>
                </div>
              </div>
              <p className="text-sm" style={{ color: "var(--text-secondary)" }}>{meta.tagline}</p>

              {isTrial && data.trial_days_remaining > 0 && (
                <div
                  className="mt-3 inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-semibold"
                  style={{ background: "var(--warning-muted, #fbbf2422)", color: "#fbbf24", border: "1px solid #fbbf2466" }}
                >
                  <Clock size={14} />
                  Триал: {data.trial_days_remaining} {data.trial_days_remaining === 1 ? "день" : data.trial_days_remaining < 5 ? "дня" : "дней"}
                </div>
              )}

              {data.is_seed_account && (
                <div className="mt-3 inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-semibold"
                     style={{ background: "#fbbf2422", color: "#fbbf24", border: "1px solid #fbbf2466" }}>
                  <Crown size={14} /> Seed account — full access
                </div>
              )}
            </div>

            {!isMaster && (
              <Link
                href="/pricing"
                className="inline-flex items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-semibold transition-all hover:scale-[1.02] whitespace-nowrap"
                style={{
                  background: "var(--accent)",
                  color: "white",
                  boxShadow: "0 0 20px var(--accent-glow)",
                }}
              >
                {isScout ? "Перейти на Pro" : "Обновить план"}
                <ArrowRight size={16} />
              </Link>
            )}
          </div>
        </motion.div>

        {/* ── USAGE — today's counters ──────────────────────────── */}
        <div>
          <h3 className="text-sm uppercase tracking-wider font-semibold mb-3 px-1" style={{ color: "var(--text-muted)" }}>
            Сегодня использовано
          </h3>
          <div className="grid sm:grid-cols-3 gap-3">
            <UsageBar
              used={data.usage.sessions_today}
              limit={data.usage.sessions_limit}
              label="Тренировки"
              icon={TrendingUp}
            />
            <UsageBar
              used={data.usage.pvp_today}
              limit={data.usage.pvp_limit}
              label="PvP-дуэли"
              icon={Zap}
            />
            <UsageBar
              used={data.usage.rag_today}
              limit={data.usage.rag_limit}
              label="RAG-запросы"
              icon={Sparkles}
            />
          </div>
        </div>

        {/* ── FEATURES — what's included in this plan ───────────── */}
        <div className="glass-panel p-6">
          <h3 className="text-sm uppercase tracking-wider font-semibold mb-4" style={{ color: "var(--text-muted)" }}>
            Что входит в план {meta.label}
          </h3>
          <div className="space-y-1.5">
            <FeatureRow
              label="AI-коуч после каждой тренировки"
              enabled={data.features.ai_coach}
              detail="Разбор слабых мест, рекомендации"
            />
            <FeatureRow
              label="Полный доступ к Wiki"
              enabled={data.features.wiki_full_access}
              detail="База знаний: возражения, скрипты, кейсы"
            />
            <FeatureRow
              label="Экспорт отчётов"
              enabled={data.features.export_reports}
              detail="CSV, PDF для руководителя"
            />
            <FeatureRow
              label="Клонирование голоса"
              enabled={data.features.voice_cloning}
            />
            <FeatureRow
              label="Турниры"
              enabled={data.features.tournaments !== "leaderboard"}
              detail={data.features.tournaments === "all" ? "Все турниры" : data.features.tournaments === "leaderboard" ? "Только рейтинг" : data.features.tournaments}
            />
            <FeatureRow
              label="Team Challenge"
              enabled={data.features.team_challenge}
              detail="Командные вызовы"
            />
            <FeatureRow
              label="Приоритетный матчмейкинг"
              enabled={data.features.priority_matchmaking}
            />
            <FeatureRow
              label="Приоритет LLM"
              enabled={data.features.llm_priority !== "low"}
              detail={`Текущий: ${data.features.llm_priority}`}
            />
          </div>
        </div>

        {/* ── FOOTER — expiry or upgrade CTA ────────────────────── */}
        {data.expires_at && (
          <div className="text-center text-xs" style={{ color: "var(--text-muted)" }}>
            План активен до {new Date(data.expires_at).toLocaleDateString("ru-RU", { day: "numeric", month: "long", year: "numeric" })}
          </div>
        )}

        {isScout && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className="glass-panel p-6 text-center"
            style={{ background: "linear-gradient(135deg, var(--accent-muted) 0%, transparent 100%)" }}
          >
            <Medal size={32} className="mx-auto mb-2" style={{ color: "var(--accent)" }} />
            <h4 className="text-lg font-bold mb-1" style={{ color: "var(--text-primary)" }}>Готов к большему?</h4>
            <p className="text-sm mb-4" style={{ color: "var(--text-secondary)" }}>
              Перейди на <span style={{ color: "#a78bfa" }}>Hunter Pro</span> — безлимитные тренировки,
              все 12 глав, все архетипы и AI-коуч.
            </p>
            <Link
              href="/pricing"
              className="inline-flex items-center gap-2 rounded-lg px-5 py-2.5 text-sm font-semibold transition-all hover:scale-[1.02]"
              style={{ background: "var(--accent)", color: "white" }}
            >
              Сравнить планы <ArrowRight size={16} />
            </Link>
          </motion.div>
        )}
      </div>
    </AuthLayout>
  );
}
