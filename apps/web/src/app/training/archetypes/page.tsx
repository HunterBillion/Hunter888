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
import { ArchetypeCard } from "@/components/training/ArchetypeCard";
import { AppIcon } from "@/components/ui/AppIcon";
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
            <Link
              href="/training"
              className="inline-flex items-center gap-1.5 text-sm font-medium mb-4"
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
              className="rounded-lg px-3 py-1.5 text-xs font-medium transition-all"
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
                  className="rounded-lg px-3 py-1.5 text-xs font-medium transition-all"
                  style={{
                    background: active ? `${g.color}20` : "var(--input-bg)",
                    color: active ? g.color : "var(--text-muted)",
                    border: `1px solid ${active ? `${g.color}50` : "var(--border-color)"}`,
                  }}
                >
                  <AppIcon emoji={g.icon} size={14} /> {g.label} ({count})
                </button>
              );
            })}
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
