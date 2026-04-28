"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { PhoneCall, Loader2, AlertTriangle } from "lucide-react";
import AuthLayout from "@/components/layout/AuthLayout";
import { ApiError, api } from "@/lib/api";
import { logger } from "@/lib/logger";

type CenterScenario = {
  id: string;
  title?: string;
  name?: string;
  description?: string;
  difficulty?: number;
  is_active?: boolean;
};

export default function CenterPage() {
  const router = useRouter();
  const [scenarios, setScenarios] = useState<CenterScenario[]>([]);
  const [loading, setLoading] = useState(true);
  const [startingId, setStartingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const raw = await api.get("/scenarios/");
        const list = Array.isArray(raw) ? raw as CenterScenario[] : [];
        if (!cancelled) setScenarios(list.filter((s) => s.is_active !== false));
      } catch (err) {
        logger.error("[center] scenarios load failed", err);
        if (!cancelled) setError("Не удалось загрузить сценарии");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const startCenterCall = async (scenarioId: string) => {
    setStartingId(scenarioId);
    setError(null);
    try {
      // C1 fix: Центр-страница — это тренировочный сценарий ("одиночный
      // звонок с фиксированным исходом"), не реальный CRM-call. Раньше
      // FE отправлял source="center" + runtime_type="center_single_call"
      // — это в backend через `derive_runtime_type` обязательно
      // требовало `real_client_id` (см. `runtime_guard_engine.py:190`,
      // guard `lead_client_required`). Без клиента кнопка валилась 400.
      //
      // Теперь шлём `source="training"` чтобы backend дерайвил
      // `training_simulation` (симуляция без CRM-привязки), при этом
      // `mode="center"` сохраняется — completion policy всё равно
      // применит правила Центра (terminal outcome required, см.
      // session_state.validate_terminal_outcome).
      //
      // Если в будущем сюда добавится client selector, тогда вернём
      // source="center" + real_client_id, и derive вернёт
      // `center_single_call` корректно.
      const session = await api.post<{ id: string }>("/training/sessions", {
        scenario_id: scenarioId,
        mode: "center",
        custom_session_mode: "center", // legacy compat
        source: "training",
      });
      router.push(`/training/${session.id}/call`);
    } catch (err) {
      if (err instanceof ApiError && err.detail?.code === "profile_incomplete") {
        router.push("/onboarding");
        return;
      }
      logger.error("[center] start failed", err);
      setError(err instanceof Error ? err.message : "Не удалось начать звонок");
      setStartingId(null);
    }
  };

  return (
    <AuthLayout>
      <main className="min-h-screen px-4 py-8" style={{ background: "var(--bg-primary)" }}>
        <div className="mx-auto max-w-5xl">
          <div className="mb-6 flex items-center justify-between gap-4">
            <div>
              <h1 className="font-display text-3xl font-semibold" style={{ color: "var(--text-primary)" }}>
                Центр
              </h1>
              <p className="mt-1 text-sm" style={{ color: "var(--text-muted)" }}>
                Одиночный звонок с фиксированным исходом.
              </p>
            </div>
          </div>

          {error && (
            <div className="mb-4 flex items-center gap-2 rounded-md border px-3 py-2 text-sm" style={{ borderColor: "var(--danger)", color: "var(--danger)" }}>
              <AlertTriangle size={16} />
              {error}
            </div>
          )}

          {loading ? (
            <div className="flex h-48 items-center justify-center">
              <Loader2 className="animate-spin" />
            </div>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {scenarios.map((scenario) => (
                <article key={scenario.id} className="rounded-lg border p-4" style={{ borderColor: "var(--border-color)", background: "var(--bg-secondary)" }}>
                  <div className="mb-2 text-base font-semibold" style={{ color: "var(--text-primary)" }}>
                    {scenario.title || scenario.name || "Сценарий"}
                  </div>
                  {scenario.description && (
                    <p className="mb-4 line-clamp-3 text-sm" style={{ color: "var(--text-muted)" }}>
                      {scenario.description}
                    </p>
                  )}
                  <button
                    type="button"
                    disabled={startingId !== null}
                    onClick={() => startCenterCall(scenario.id)}
                    className="inline-flex w-full items-center justify-center gap-2 rounded-md px-3 py-2 text-sm font-semibold text-white transition disabled:opacity-50"
                    style={{ background: "var(--accent)" }}
                  >
                    {startingId === scenario.id ? <Loader2 size={16} className="animate-spin" /> : <PhoneCall size={16} />}
                    Начать звонок
                  </button>
                </article>
              ))}
            </div>
          )}
        </div>
      </main>
    </AuthLayout>
  );
}
