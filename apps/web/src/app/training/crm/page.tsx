"use client";

import { useState, useEffect, useCallback } from "react";
import { motion } from "framer-motion";
import {
  Gamepad2,
  Loader2,
  RefreshCw,
  Sparkles,
  Layers3,
  Activity,
} from "lucide-react";
import { BackButton } from "@/components/ui/BackButton";
import { api } from "@/lib/api";
import AuthLayout from "@/components/layout/AuthLayout";
import { GameStoryCard } from "@/components/game-crm/GameStoryCard";
import { GamePortfolioStats } from "@/components/game-crm/GamePortfolioStats";
import type { GameStory, GamePortfolioStats as PortfolioStats } from "@/types";
import { useNotificationStore } from "@/stores/useNotificationStore";
import { logger } from "@/lib/logger";

export default function GameCRMPage() {
  const [stories, setStories] = useState<GameStory[]>([]);
  const [stats, setStats] = useState<PortfolioStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [statsLoading, setStatsLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [period, setPeriod] = useState("all");
  const [showCompleted, setShowCompleted] = useState<boolean | null>(null);

  // ── Fetch stories ──
  const fetchStories = useCallback(async () => {
    try {
      const params = new URLSearchParams({ limit: "100" });
      if (showCompleted === true) params.set("completed", "true");
      if (showCompleted === false) params.set("completed", "false");

      const data = await api.get(`/game/clients/stories?${params}`);
      setStories(data.items || []);
    } catch (err) {
      useNotificationStore.getState().addToast({
        title: "Ошибка загрузки",
        body: "Не удалось загрузить истории. Попробуйте обновить страницу.",
        type: "error",
      });
      logger.error("Failed to load stories:", err);
    }
    setLoading(false);
  }, [showCompleted]);

  // ── Fetch portfolio stats ──
  const fetchStats = useCallback(async () => {
    setStatsLoading(true);
    try {
      const data: PortfolioStats = await api.get(`/game/clients/portfolio/stats?period=${period}`);
      setStats(data);
    } catch (err) {
      logger.error("Failed to load portfolio stats:", err);
    }
    setStatsLoading(false);
  }, [period]);

  useEffect(() => {
    fetchStories();
  }, [fetchStories]);

  useEffect(() => {
    fetchStats();
  }, [fetchStats]);

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    await Promise.all([fetchStories(), fetchStats()]);
    setRefreshing(false);
  }, [fetchStories, fetchStats]);

  const activeStories = stories.filter((s) => !s.is_completed);
  const completedStories = stories.filter((s) => s.is_completed);

  return (
    <AuthLayout>
      <div className="min-h-[calc(100vh-64px)] bg-[radial-gradient(circle_at_top,rgba(99,102,241,0.14),transparent_32%),linear-gradient(180deg,#040405_0%,#0a0a0d_45%,#09090b_100%)]">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          className="px-4 pt-6 pb-4 shrink-0"
        >
          <div className="mx-auto max-w-[1200px]">
            <div
              className="overflow-hidden rounded-[30px] border p-6"
              style={{ background: "linear-gradient(180deg, rgba(8,8,10,0.96), rgba(15,15,20,0.94))", borderColor: "rgba(255,255,255,0.08)" }}
            >
              <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
                <div className="max-w-2xl">
                  <div className="flex items-center gap-3">
                    <BackButton href="/training" label="К тренировке" />
                    <div className="flex h-11 w-11 items-center justify-center rounded-2xl" style={{ background: "rgba(99,102,241,0.16)", border: "1px solid rgba(99,102,241,0.26)" }}>
                      <Gamepad2 size={20} style={{ color: "var(--accent)" }} />
                    </div>
                    <div>
                      <div className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--accent)" }}>
                        AI Client Matrix
                      </div>
                      <h1
                        className="font-display text-3xl font-bold tracking-[0.12em]"
                        style={{ color: "var(--text-primary)" }}
                      >
                        ИГРОВАЯ CRM
                      </h1>
                    </div>
                  </div>
                  <p className="mt-4 max-w-xl text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>
                    Здесь живут не отдельные звонки, а все ваши AI-клиенты как длинные истории: прогресс, напряжение, события между контактами и качество прохождения по каждому сюжету.
                  </p>
                </div>

                <div className="grid grid-cols-3 gap-3 lg:min-w-[360px]">
                  {[
                    { label: "Историй", value: stories.length, icon: Layers3 },
                    { label: "Активных", value: activeStories.length, icon: Activity },
                    { label: "Continuity", value: completedStories.length > 0 ? `${completedStories.length}/${stories.length}` : stories.length > 0 ? `0/${stories.length}` : "0", icon: Sparkles },
                  ].map((item) => (
                    <div key={item.label} className="rounded-2xl p-4" style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.06)" }}>
                      <item.icon size={14} style={{ color: "var(--accent)" }} />
                      <div className="mt-2 text-2xl font-semibold" style={{ color: "var(--text-primary)" }}>
                        {item.value}
                      </div>
                      <div className="text-xs font-medium uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>
                        {item.label}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
              <div className="mt-5 flex flex-col gap-3 border-t pt-4 sm:flex-row sm:items-center sm:justify-between" style={{ borderColor: "rgba(255,255,255,0.06)" }}>
                <div className="flex gap-1.5">
                  {[
                    { value: null, label: "Все истории" },
                    { value: false, label: "Активные" },
                    { value: true, label: "Завершённые" },
                  ].map((opt) => (
                    <button
                      key={String(opt.value)}
                      onClick={() => setShowCompleted(opt.value as boolean | null)}
                      className="rounded-xl px-3 py-2 text-xs font-medium uppercase tracking-wide transition-colors"
                      style={{
                        background: showCompleted === opt.value ? "var(--accent)" : "rgba(255,255,255,0.03)",
                        color: showCompleted === opt.value ? "#000" : "var(--text-muted)",
                        border: `1px solid ${showCompleted === opt.value ? "var(--accent)" : "rgba(255,255,255,0.06)"}`,
                      }}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>

                <motion.button
                  onClick={handleRefresh}
                  className="flex items-center justify-center gap-2 rounded-xl px-4 py-2 text-xs font-medium uppercase tracking-wide"
                  style={{
                    background: "rgba(255,255,255,0.03)",
                    border: "1px solid rgba(255,255,255,0.06)",
                    color: "var(--text-muted)",
                  }}
                  whileTap={{ scale: 0.97 }}
                >
                  <RefreshCw size={11} className={refreshing ? "animate-spin" : ""} />
                  Обновить поток
                </motion.button>
              </div>
            </div>
          </div>
        </motion.div>

        {/* Content */}
        <div className="flex-1 px-4 pb-8 overflow-y-auto">
          <div className="mx-auto max-w-[1200px] space-y-8">
            {/* Portfolio Stats */}
            <GamePortfolioStats
              stats={stats}
              loading={statsLoading}
              period={period}
              onPeriodChange={setPeriod}
            />

            {/* Stories Grid */}
            {loading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2
                  size={24}
                  className="animate-spin"
                  style={{ color: "var(--accent)" }}
                />
              </div>
            ) : stories.length === 0 ? (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="text-center py-16"
              >
                <Gamepad2
                  size={40}
                  className="mx-auto mb-3"
                  style={{ color: "var(--text-muted)", opacity: 0.4 }}
                />
                <p
                  className="text-sm"
                  style={{ color: "var(--text-muted)" }}
                >
                  Нет игровых клиентов
                </p>
                <p
                  className="text-xs mt-1"
                  style={{ color: "var(--text-muted)", opacity: 0.7 }}
                >
                  Начните тренировку чтобы создать историю
                </p>
              </motion.div>
            ) : (
              <>
                {/* Active stories */}
                {activeStories.length > 0 && (
                  <div>
                    <h2
                      className="mb-3 text-xs font-semibold uppercase tracking-wide"
                      style={{ color: "var(--text-muted)" }}
                    >
                      Активные истории ({activeStories.length})
                    </h2>
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                      {activeStories.map((story, i) => (
                        <motion.div
                          key={story.id}
                          initial={{ opacity: 0, y: 12 }}
                          animate={{ opacity: 1, y: 0 }}
                          transition={{ delay: i * 0.04 }}
                        >
                          <GameStoryCard story={story} />
                        </motion.div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Completed stories */}
                {completedStories.length > 0 && showCompleted !== false && (
                  <div>
                    <h2
                      className="mb-3 text-xs font-semibold uppercase tracking-wide"
                      style={{ color: "var(--text-muted)" }}
                    >
                      Завершённые ({completedStories.length})
                    </h2>
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                      {completedStories.map((story, i) => (
                        <motion.div
                          key={story.id}
                          initial={{ opacity: 0, y: 12 }}
                          animate={{ opacity: 1, y: 0 }}
                          transition={{ delay: i * 0.04 }}
                        >
                          <GameStoryCard story={story} />
                        </motion.div>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </AuthLayout>
  );
}
