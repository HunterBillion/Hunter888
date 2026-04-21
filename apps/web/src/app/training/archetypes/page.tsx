"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Lock, Search } from "lucide-react";
import Link from "next/link";
import { BackButton } from "@/components/ui/BackButton";
import AuthLayout from "@/components/layout/AuthLayout";
import {
  ARCHETYPES,
  ARCHETYPE_GROUPS,
  getTierColor,
  getDifficultyColor,
} from "@/lib/archetypes";
import type { ArchetypeInfo, ArchetypeGroupInfo } from "@/lib/archetypes";
import { ArchetypeCard } from "@/components/training/ArchetypeCard";
import { GROUP_ICONS } from "@/lib/groupIcons";
import type { ArchetypeGroup } from "@/types";
import { useGamificationStore } from "@/stores/useGamificationStore";

const GROUP_KEYS: ArchetypeGroup[] = [
  "resistance",
  "emotional",
  "control",
  "avoidance",
  "special",
  "cognitive",
  "social",
  "temporal",
  "professional",
  "compound",
];

const TIER_LABELS: Record<number, string> = {
  1: "Tier 1",
  2: "Tier 2",
  3: "Tier 3",
  4: "Tier 4",
};

export default function ArchetypesPage() {
  const { level, fetchProgress } = useGamificationStore();
  const [selectedGroup, setSelectedGroup] = useState<ArchetypeGroup | "all">("all");
  const [search, setSearch] = useState("");

  useEffect(() => {
    fetchProgress();
  }, [fetchProgress]);

  const filtered = ARCHETYPES.filter((a) => {
    if (selectedGroup !== "all" && a.group !== selectedGroup) return false;
    if (search) {
      const q = search.toLowerCase();
      return (
        a.name.toLowerCase().includes(q) ||
        a.subtitle.toLowerCase().includes(q) ||
        a.code.toLowerCase().includes(q) ||
        a.description.toLowerCase().includes(q)
      );
    }
    return true;
  });

  const unlocked = ARCHETYPES.filter((a) => a.unlock_level <= level).length;

  return (
    <AuthLayout>
      <div className="panel-grid-bg min-h-screen">
        <div className="app-page">
          {/* Header */}
          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
            <BackButton href="/training" label="Тренировки" />

            <div className="flex items-start justify-between flex-wrap gap-4">
              <div>
                <h1
                  className="font-display text-2xl font-bold tracking-wide"
                  style={{ color: "var(--text-primary)" }}
                >
                  Каталог архетипов
                </h1>
                <p className="mt-1 text-sm" style={{ color: "var(--text-muted)" }}>
                  {unlocked} / {ARCHETYPES.length} разблокировано (уровень {level})
                </p>
              </div>
            </div>
          </motion.div>

          {/* 2026-04-17 redesign: search + category chips в одной большой панели.
              Поиск широкий (full-width), чипы под ним в горизонтальной полосе
              с горизонтальным скроллом на узких экранах — чтобы 10 категорий
              + "Все" помещались в 1 ряд без неряшливого wrap. */}
          <div
            className="mt-6 rounded-xl border p-3 sm:p-4 space-y-3"
            style={{
              background: "var(--input-bg)",
              borderColor: "var(--border-color)",
            }}
          >
            {/* Big search bar */}
            <div className="relative">
              <Search
                size={18}
                className="absolute left-4 top-1/2 -translate-y-1/2"
                style={{ color: "var(--text-muted)" }}
              />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Поиск по имени, коду или описанию архетипа…"
                className="vh-input w-full pl-12 pr-4 py-3 text-base"
                style={{ minHeight: "48px" }}
              />
              {search && (
                <button
                  onClick={() => setSearch("")}
                  aria-label="Очистить поиск"
                  className="absolute right-3 top-1/2 -translate-y-1/2 px-2 py-1 text-xs"
                  style={{ color: "var(--text-muted)" }}
                >
                  ✕
                </button>
              )}
            </div>

            {/* Category row — horizontal scroll on narrow screens so chips
                never wrap into multiple messy rows. */}
            <div className="overflow-x-auto -mx-1 px-1 pb-1 [scrollbar-width:thin]">
              <div className="flex gap-1.5 items-center">
                <button
                  onClick={() => setSelectedGroup("all")}
                  className="shrink-0 rounded-lg px-3 py-1.5 text-xs font-medium transition-all whitespace-nowrap"
                  style={{
                    background: selectedGroup === "all" ? "var(--accent)" : "transparent",
                    color: selectedGroup === "all" ? "white" : "var(--text-muted)",
                    border: `1px solid ${selectedGroup === "all" ? "var(--accent)" : "var(--border-color)"}`,
                  }}
                >
                  Все ({ARCHETYPES.length})
                </button>
                {GROUP_KEYS.map((gk) => {
                  const g = ARCHETYPE_GROUPS[gk];
                  const count = ARCHETYPES.filter((a) => a.group === gk).length;
                  const active = selectedGroup === gk;
                  const I = GROUP_ICONS[g.icon];
                  return (
                    <button
                      key={gk}
                      onClick={() => setSelectedGroup(gk)}
                      className="shrink-0 rounded-lg px-3 py-1.5 text-xs font-medium transition-all whitespace-nowrap flex items-center gap-1.5"
                      style={{
                        background: active ? `${g.color}20` : "transparent",
                        color: active ? g.color : "var(--text-muted)",
                        border: `1px solid ${active ? `${g.color}50` : "var(--border-color)"}`,
                      }}
                    >
                      {I ? <I size={14} weight="duotone" style={{ color: active ? g.color : "var(--text-muted)" }} /> : null}
                      {g.label} ({count})
                    </button>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Grid */}
          <div className="mt-6 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {filtered.map((arch) => (
              <ArchetypeCard key={arch.code} arch={arch} size="medium" />
            ))}
          </div>

          {filtered.length === 0 && (
            <div className="text-center py-16">
              <p className="text-sm" style={{ color: "var(--text-muted)" }}>
                Архетипы не найдены
              </p>
            </div>
          )}
        </div>
      </div>
    </AuthLayout>
  );
}
