"use client";

/**
 * /dev/sounds-preview — Фаза 8: каталог всех звуков + sandbox для теста
 * новых ползунков громкости.
 *
 * 2026-05-01: рендерит SoundSettings (как на /settings) + ниже сетку
 * кнопок-плееров для всех известных SoundName, сгруппированных по
 * категории. Полезно проверить нормализацию: все звуки одной категории
 * на одинаковой громкости должны звучать схоже.
 */

import * as React from "react";
import { motion } from "framer-motion";
import { ArenaBackground } from "@/components/pvp/ArenaBackground";
import { SoundSettings } from "@/components/settings/SoundSettings";
import { useSound, type SoundName } from "@/hooks/useSound";

interface PreviewSpec {
  name: SoundName;
  label: string;
  category: string;
  color: string;
}

const PREVIEWS: PreviewSpec[] = [
  // Arena combat
  { name: "ko", label: "KO! (Phase 1 Victory)", category: "Бой", color: "var(--danger)" },
  { name: "hit", label: "Hit (judge.score)", category: "Бой", color: "var(--danger)" },
  { name: "heartbeat", label: "Heartbeat (≤5s)", category: "Бой", color: "var(--danger)" },
  { name: "swap", label: "Swap (смена ролей)", category: "Бой", color: "var(--danger)" },
  // Match flow
  { name: "match_start", label: "Match Start", category: "Матч", color: "var(--accent)" },
  { name: "challenge", label: "Challenge", category: "Матч", color: "var(--accent)" },
  { name: "pvpMatch", label: "PvP Match Found", category: "Матч", color: "var(--accent)" },
  // Outcomes
  { name: "victory", label: "Victory", category: "Финал", color: "var(--gf-xp)" },
  { name: "defeat", label: "Defeat", category: "Финал", color: "var(--text-muted)" },
  { name: "rank_up", label: "Rank Up", category: "Финал", color: "var(--gf-xp)" },
  // Quiz
  { name: "correct", label: "Correct", category: "Квиз", color: "var(--success)" },
  { name: "incorrect", label: "Incorrect", category: "Квиз", color: "var(--danger)" },
  { name: "tick", label: "Tick", category: "Квиз", color: "var(--warning)" },
  { name: "streak", label: "Streak", category: "Квиз", color: "var(--accent)" },
  // Reward
  { name: "success", label: "Success", category: "Награда", color: "var(--success)" },
  { name: "epic", label: "Epic", category: "Награда", color: "var(--accent)" },
  { name: "legendary", label: "Legendary", category: "Награда", color: "var(--gf-xp)" },
  { name: "fail", label: "Fail", category: "Награда", color: "var(--text-muted)" },
  // UI
  { name: "click", label: "Click", category: "UI", color: "var(--info)" },
  { name: "hover", label: "Hover", category: "UI", color: "var(--info)" },
  { name: "notification", label: "Notification", category: "UI", color: "var(--info)" },
  { name: "xp", label: "XP", category: "UI", color: "var(--info)" },
  { name: "levelUp", label: "Level Up", category: "UI", color: "var(--info)" },
  { name: "levelup", label: "Levelup (alt)", category: "UI", color: "var(--info)" },
  { name: "countdownTick", label: "Countdown Tick", category: "UI", color: "var(--info)" },
];

export default function SoundsPreviewPage() {
  const { playSound } = useSound();
  const grouped = React.useMemo(() => {
    const map = new Map<string, PreviewSpec[]>();
    for (const p of PREVIEWS) {
      if (!map.has(p.category)) map.set(p.category, []);
      map.get(p.category)!.push(p);
    }
    return map;
  }, []);

  return (
    <ArenaBackground tier="diamond" className="min-h-screen px-4 py-6 sm:px-8 sm:py-10">
      <div className="relative mx-auto max-w-5xl space-y-8">
        <header>
          <h1
            className="font-pixel"
            style={{
              color: "var(--text-primary)",
              fontSize: 32,
              letterSpacing: "0.18em",
              textTransform: "uppercase",
              lineHeight: 1.05,
            }}
          >
            Звуки — Фаза 8
          </h1>
          <p
            className="mt-2 font-pixel"
            style={{ color: "var(--text-muted)", fontSize: 14, letterSpacing: "0.1em" }}
          >
            Master + категории + нормализация. То же что на /settings, но полный каталог.
          </p>
        </header>

        {/* Sound settings */}
        <section
          className="p-5"
          style={{
            background: "var(--bg-panel)",
            outline: "2px solid var(--accent)",
            outlineOffset: -2,
            boxShadow: "4px 4px 0 0 var(--accent)",
          }}
        >
          <h2
            className="font-pixel mb-4"
            style={{
              color: "var(--text-primary)",
              fontSize: 18,
              letterSpacing: "0.18em",
              textTransform: "uppercase",
            }}
          >
            ▸ Регулировка
          </h2>
          <SoundSettings />
        </section>

        {/* Sound catalog */}
        {Array.from(grouped.entries()).map(([cat, items]) => (
          <section
            key={cat}
            className="p-5"
            style={{
              background: "var(--bg-panel)",
              outline: "2px solid var(--border-color)",
              outlineOffset: -2,
              boxShadow: "3px 3px 0 0 var(--border-color)",
            }}
          >
            <h3
              className="font-pixel mb-4"
              style={{
                color: "var(--text-primary)",
                fontSize: 16,
                letterSpacing: "0.18em",
                textTransform: "uppercase",
              }}
            >
              ▸ {cat}
            </h3>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
              {items.map((p) => (
                <motion.button
                  key={p.name}
                  type="button"
                  onClick={() => playSound(p.name)}
                  whileHover={{ x: -1, y: -1 }}
                  whileTap={{ x: 2, y: 2 }}
                  className="font-pixel text-left p-3"
                  style={{
                    background: "var(--bg-secondary)",
                    color: p.color,
                    border: `2px solid ${p.color}`,
                    borderRadius: 0,
                    fontSize: 12,
                    letterSpacing: "0.12em",
                    textTransform: "uppercase",
                    boxShadow: `2px 2px 0 0 ${p.color}`,
                    cursor: "pointer",
                    lineHeight: 1.2,
                  }}
                >
                  ▶ {p.label}
                </motion.button>
              ))}
            </div>
          </section>
        ))}
      </div>
    </ArenaBackground>
  );
}
