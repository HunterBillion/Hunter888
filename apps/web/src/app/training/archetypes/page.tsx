"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Lock, ArrowLeft, Search } from "lucide-react";
import Link from "next/link";
import AuthLayout from "@/components/layout/AuthLayout";
import {
  ARCHETYPES,
  ARCHETYPE_GROUPS,
  getTierColor,
  getDifficultyColor,
} from "@/lib/archetypes";
import type { ArchetypeInfo, ArchetypeGroupInfo } from "@/lib/archetypes";
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
        <div className="mx-auto max-w-6xl px-4 py-8">
          {/* Header */}
          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
            <Link
              href="/training"
              className="inline-flex items-center gap-1.5 text-sm font-mono mb-4"
              style={{ color: "var(--text-muted)" }}
            >
              <ArrowLeft size={14} /> Тренировки
            </Link>

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

              {/* Search */}
              <div className="relative w-full sm:w-64">
                <Search
                  size={14}
                  className="absolute left-3 top-1/2 -translate-y-1/2"
                  style={{ color: "var(--text-muted)" }}
                />
                <input
                  type="text"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Поиск..."
                  className="vh-input pl-9 w-full"
                />
              </div>
            </div>
          </motion.div>

          {/* Group tabs */}
          <div className="mt-6 flex gap-1.5 flex-wrap">
            <button
              onClick={() => setSelectedGroup("all")}
              className="rounded-lg px-3 py-1.5 text-xs font-mono transition-all"
              style={{
                background: selectedGroup === "all" ? "var(--accent)" : "var(--input-bg)",
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
              return (
                <button
                  key={gk}
                  onClick={() => setSelectedGroup(gk)}
                  className="rounded-lg px-3 py-1.5 text-xs font-mono transition-all"
                  style={{
                    background: active ? `${g.color}20` : "var(--input-bg)",
                    color: active ? g.color : "var(--text-muted)",
                    border: `1px solid ${active ? `${g.color}50` : "var(--border-color)"}`,
                  }}
                >
                  {g.icon} {g.label} ({count})
                </button>
              );
            })}
          </div>

          {/* Grid */}
          <div className="mt-6 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {filtered.map((arch, i) => {
              const isLocked = arch.unlock_level > level;
              const group = ARCHETYPE_GROUPS[arch.group];
              const tierColor = getTierColor(arch.tier);
              const diffColor = getDifficultyColor(arch.difficulty);

              return (
                <motion.div
                  key={arch.code}
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: Math.min(i * 0.02, 0.4) }}
                  className="relative overflow-hidden rounded-2xl"
                  style={{
                    background: "var(--glass-bg)",
                    border: `1px solid ${isLocked ? "var(--border-color)" : `${group.color}25`}`,
                    opacity: isLocked ? 0.55 : 1,
                    filter: isLocked ? "grayscale(0.6)" : "none",
                  }}
                >
                  {/* Top accent */}
                  <div
                    className="h-1"
                    style={{
                      background: isLocked
                        ? "var(--border-color)"
                        : `linear-gradient(90deg, ${group.color}, ${tierColor})`,
                    }}
                  />

                  <div className="p-4">
                    {/* Row 1: icon + name */}
                    <div className="flex items-start gap-3 mb-2">
                      <div
                        className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0 text-lg"
                        style={{
                          background: isLocked
                            ? "var(--input-bg)"
                            : `linear-gradient(135deg, ${group.color}, ${group.color}BB)`,
                          color: isLocked ? "var(--text-muted)" : "white",
                        }}
                      >
                        {isLocked ? <Lock size={16} /> : arch.icon}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div
                          className="font-display text-base font-bold leading-tight"
                          style={{ color: isLocked ? "var(--text-muted)" : "var(--text-primary)" }}
                        >
                          {arch.name}
                        </div>
                        <div
                          className="text-xs mt-0.5"
                          style={{ color: "var(--text-muted)" }}
                        >
                          {arch.subtitle}
                        </div>
                      </div>

                      {/* Tier badge */}
                      <span
                        className="text-xs font-mono px-2 py-0.5 rounded-md shrink-0"
                        style={{
                          background: `${tierColor}15`,
                          color: tierColor,
                          border: `1px solid ${tierColor}30`,
                        }}
                      >
                        {TIER_LABELS[arch.tier]}
                      </span>
                    </div>

                    {/* Description */}
                    <p
                      className="text-sm leading-relaxed line-clamp-2 mb-3"
                      style={{ color: "var(--text-secondary)" }}
                    >
                      {arch.description}
                    </p>

                    {/* Badges row */}
                    <div className="flex items-center gap-2 flex-wrap">
                      {/* Group */}
                      <span
                        className="text-xs font-mono px-2 py-0.5 rounded-md"
                        style={{
                          background: `${group.color}12`,
                          color: group.color,
                          border: `1px solid ${group.color}25`,
                        }}
                      >
                        {group.label}
                      </span>

                      {/* Difficulty */}
                      <span
                        className="text-xs font-mono px-2 py-0.5 rounded-md"
                        style={{
                          background: `${diffColor}12`,
                          color: diffColor,
                          border: `1px solid ${diffColor}25`,
                        }}
                      >
                        {arch.difficulty}/10
                      </span>

                      {/* Lock info */}
                      {isLocked && (
                        <span
                          className="ml-auto flex items-center gap-1 text-xs font-mono"
                          style={{ color: "var(--text-muted)" }}
                        >
                          <Lock size={10} /> Уровень {arch.unlock_level}
                        </span>
                      )}
                    </div>
                  </div>
                </motion.div>
              );
            })}
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
