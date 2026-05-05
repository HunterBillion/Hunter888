"use client";

/**
 * AIRemembersBanner — PR-A (cross-session memory).
 *
 * Видимая «панель памяти» наверху CRM-карточки клиента: показывает
 * ровно тот текст, который backend инжектит в system_prompt при
 * следующей тренировке с этим клиентом. Это превращает CRM из
 * декорации в работающий контекст — продажник видит, что ИИ-«клиент»
 * помнит его, и понимает на чём ИИ строит реакции в новой сессии.
 *
 * Self-hides если:
 *   - API ответил summary=null (первая встреча)
 *   - запрос упал (не поломаем layout — CRM работает без памяти)
 */

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Brain, ChevronDown, ChevronUp } from "lucide-react";
import { api } from "@/lib/api";
import { logger } from "@/lib/logger";

interface Props {
  clientId: string;
}

interface AIMemoryResponse {
  summary: string | null;
  facts: Record<string, unknown>;
  // PR-A.1: count of prior COMPLETED sessions for this (manager, client)
  // pair. Rendered as a leading chip («Было 3 звонка») so the returning-
  // relationship signal is visible at a glance without parsing summary.
  total_completed?: number;
}

const SLOT_LABELS: Record<string, string> = {
  full_name: "Имя",
  phone: "Телефон",
  email: "Email",
  city: "Город",
  total_debt: "Сумма долга",
  creditors: "Кредиторы",
  income: "Доход",
  family_status: "Семья",
  property_status: "Имущество",
};

function factPreview(facts: Record<string, unknown>): { label: string; value: string }[] {
  const out: { label: string; value: string }[] = [];
  for (const [slot, raw] of Object.entries(facts)) {
    if (out.length >= 4) break;
    const label = SLOT_LABELS[slot];
    if (!label) continue;
    let value: string | null = null;
    if (typeof raw === "string") value = raw;
    else if (raw && typeof raw === "object") {
      const v = (raw as { value?: unknown }).value;
      if (typeof v === "string" || typeof v === "number") value = String(v);
    }
    if (value) out.push({ label, value });
  }
  return out;
}

export function AIRemembersBanner({ clientId }: Props) {
  const [data, setData] = useState<AIMemoryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    // Reset local view BEFORE the new request so navigating between
    // clients (A → B) does not flash A's memory while B's request is
    // in flight. Without this reset the previous client's facts hang
    // around for the duration of the network round-trip.
    setData(null);
    setLoading(true);
    setExpanded(false);
    (async () => {
      try {
        const resp = await api.get<AIMemoryResponse>(`/clients/${clientId}/ai-memory`);
        if (!cancelled) setData(resp);
      } catch (err) {
        // Soft-fail: 403 (methodologist), 404 (unbound client), or
        // network blip — banner self-hides. Non-essential data path.
        logger.warn("ai-memory fetch failed", err);
        if (!cancelled) setData(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [clientId]);

  if (loading) return null;
  if (!data || (!data.summary && Object.keys(data.facts || {}).length === 0)) return null;

  const facts = factPreview(data.facts || {});
  const hasFacts = facts.length > 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      className="rounded-xl border border-violet-500/30 bg-gradient-to-r from-violet-500/10 to-purple-500/5 p-4 mb-4"
      style={{ backdropFilter: "blur(8px)" }}
    >
      <div className="flex items-start gap-3">
        <div className="flex-shrink-0 mt-0.5">
          <Brain size={20} className="text-violet-400" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <span className="text-xs font-semibold text-violet-300 uppercase tracking-wider">
              ИИ помнит этого клиента
            </span>
            {/* PR-A.1: leading «N-й звонок» chip — most legible signal of
                a returning relationship. Hidden when total_completed < 1
                so a fresh client (banner showing only persona facts)
                doesn't get a misleading «1 звонок» label. */}
            {data.total_completed !== undefined && data.total_completed >= 1 && (
              <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-violet-500/30 text-violet-100 font-semibold">
                {data.total_completed === 1
                  ? "Был 1 звонок"
                  : `Было ${data.total_completed} звонков`}
              </span>
            )}
            {hasFacts && (
              <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-violet-500/20 text-violet-200">
                {Object.keys(data.facts).length} фактов
              </span>
            )}
          </div>
          {data.summary && (
            <p className="text-sm text-white/85 leading-relaxed">{data.summary}</p>
          )}
          {!data.summary && hasFacts && (
            <p className="text-sm text-white/70">
              Прошлой завершённой сессии нет, но ИИ уже знает {facts.length} ключевых фактов.
            </p>
          )}
          <AnimatePresence initial={false}>
            {expanded && hasFacts && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                className="overflow-hidden mt-3"
              >
                <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs">
                  {facts.map((f) => (
                    <div key={f.label} className="flex gap-2">
                      <span className="text-white/50">{f.label}:</span>
                      <span className="text-white/90 truncate">{f.value}</span>
                    </div>
                  ))}
                </div>
                <div className="mt-2 text-[11px] text-white/50">
                  ИИ-клиент учитывает эти факты в новой тренировке — не нужно повторно
                  представляться или объяснять контекст.
                </div>
              </motion.div>
            )}
          </AnimatePresence>
          {hasFacts && (
            <button
              type="button"
              onClick={() => setExpanded((v) => !v)}
              className="mt-2 inline-flex items-center gap-1 text-xs text-violet-300 hover:text-violet-200 transition-colors"
            >
              {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
              {expanded ? "Свернуть факты" : "Показать факты"}
            </button>
          )}
        </div>
      </div>
    </motion.div>
  );
}
