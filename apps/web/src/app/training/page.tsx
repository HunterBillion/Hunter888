"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { Scenario } from "@/types";

export default function TrainingPage() {
  const router = useRouter();
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get("/scenarios/").then(setScenarios).catch(console.error).finally(() => setLoading(false));
  }, []);

  const startTraining = async (scenarioId: string) => {
    try {
      const session = await api.post("/training/sessions", {
        scenario_id: scenarioId,
      });
      router.push(`/training/${session.id}`);
    } catch (err) {
      console.error("Failed to start training:", err);
    }
  };

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-lg text-gray-500">Загрузка сценариев...</div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <h1 className="text-2xl font-bold">Выберите сценарий</h1>
      <p className="mt-2 text-gray-600">
        Начните тренировку с одним из доступных AI-персонажей
      </p>

      <div className="mt-8 grid gap-6 sm:grid-cols-2">
        {scenarios.map((scenario) => (
          <div
            key={scenario.id}
            className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm"
          >
            <h3 className="text-lg font-semibold">{scenario.title}</h3>
            <p className="mt-2 text-sm text-gray-600">{scenario.description}</p>

            <div className="mt-4 flex items-center gap-4 text-sm text-gray-500">
              <span>Сложность: {scenario.difficulty}/10</span>
              <span>{scenario.estimated_duration_minutes} мин</span>
            </div>

            <button
              onClick={() => startTraining(scenario.id)}
              className="mt-4 w-full rounded-md bg-primary-600 px-4 py-2 text-white hover:bg-primary-700"
            >
              Начать тренировку
            </button>
          </div>
        ))}

        {scenarios.length === 0 && (
          <div className="col-span-2 text-center text-gray-500">
            Сценарии пока не добавлены
          </div>
        )}
      </div>
    </div>
  );
}
