"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { Scenario } from "@/types";

const DIFFICULTY_COLORS: Record<string, string> = {
  easy: "text-vh-green border-vh-green/30",
  medium: "text-yellow-400 border-yellow-400/30",
  hard: "text-vh-red border-vh-red/30",
};

function getDifficultyLabel(d: number): { label: string; color: string } {
  if (d <= 3) return { label: "Легко", color: DIFFICULTY_COLORS.easy };
  if (d <= 6) return { label: "Средне", color: DIFFICULTY_COLORS.medium };
  return { label: "Сложно", color: DIFFICULTY_COLORS.hard };
}

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
        <div className="text-lg text-gray-500 animate-pulse">
          Загрузка сценариев...
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <h1 className="text-2xl font-display font-bold text-vh-purple tracking-wider">
        ВЫБЕРИТЕ СЦЕНАРИЙ
      </h1>
      <p className="mt-2 text-gray-400 text-sm">
        Начните тренировку с одним из доступных AI-персонажей
      </p>

      <div className="mt-8 grid gap-6 sm:grid-cols-2">
        {scenarios.map((scenario) => {
          const diff = getDifficultyLabel(scenario.difficulty);
          return (
            <div
              key={scenario.id}
              className="glass-panel p-6 hover:border-vh-purple/50 transition-all duration-300 group"
            >
              <h3 className="text-lg font-display font-semibold text-gray-100 group-hover:text-vh-purple transition-colors">
                {scenario.title}
              </h3>
              <p className="mt-2 text-sm text-gray-400">{scenario.description}</p>

              <div className="mt-4 flex items-center gap-4 text-sm">
                <span className={`px-2 py-0.5 rounded border text-xs ${diff.color}`}>
                  {diff.label} ({scenario.difficulty}/10)
                </span>
                <span className="text-gray-500">
                  {scenario.estimated_duration_minutes} мин
                </span>
              </div>

              <button
                onClick={() => startTraining(scenario.id)}
                className="vh-btn-primary w-full mt-4"
              >
                Начать тренировку
              </button>
            </div>
          );
        })}

        {scenarios.length === 0 && (
          <div className="col-span-2 text-center text-gray-500 py-12">
            Сценарии пока не добавлены
          </div>
        )}
      </div>
    </div>
  );
}
