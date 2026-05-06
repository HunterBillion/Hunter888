"use client";

import { motion } from "framer-motion";

export type TamagotchiPet = "lion" | "tiger" | "eagle";

interface Props {
  pet: TamagotchiPet;
  hunger?: number;
  happiness?: number;
  energy?: number;
  compact?: boolean;
}

const PET_CONFIG: Record<TamagotchiPet, {
  label: string;
  shell: string;
  shellGlow: string;
  heartEmoji: string;
  sprite: string;
}> = {
  lion: {
    label: "ЛЕВ",
    shell: "linear-gradient(145deg, #ff6b9d 0%, #c44569 50%, #ff6b9d 100%)",
    shellGlow: "rgba(255,107,157,0.4)",
    heartEmoji: "❤️",
    sprite: `url("data:image/svg+xml,${encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect fill="%23f5a623" x="16" y="24" width="32" height="28" rx="4"/><rect fill="%23ffa502" x="12" y="16" width="40" height="20" rx="8"/><circle fill="%232c3e50" cx="26" cy="32" r="3"/><circle fill="%232c3e50" cx="38" cy="32" r="3"/><path fill="%232c3e50" d="M28 38 Q32 42 36 38"/><rect fill="%23f5a623" x="20" y="8" width="6" height="10" rx="2"/><rect fill="%23f5a623" x="38" y="8" width="6" height="10" rx="2"/><rect fill="%23f5a623" x="14" y="50" width="8" height="12" rx="2"/><rect fill="%23f5a623" x="42" y="50" width="8" height="12" rx="2"/></svg>')}")`,
  },
  tiger: {
    label: "ТИГР",
    shell: "linear-gradient(145deg, #ff9f43 0%, #ee5a24 50%, #ff9f43 100%)",
    shellGlow: "rgba(255,159,67,0.4)",
    heartEmoji: "💛",
    sprite: `url("data:image/svg+xml,${encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect fill="%23ff6b35" x="16" y="24" width="32" height="28" rx="4"/><rect fill="%23f7931e" x="12" y="16" width="40" height="20" rx="8"/><rect fill="%232c3e50" x="18" y="18" width="4" height="12"/><rect fill="%232c3e50" x="26" y="18" width="4" height="12"/><rect fill="%232c3e50" x="34" y="18" width="4" height="12"/><rect fill="%232c3e50" x="42" y="18" width="4" height="12"/><circle fill="%232c3e50" cx="26" cy="32" r="3"/><circle fill="%232c3e50" cx="38" cy="32" r="3"/><path fill="%232c3e50" d="M28 38 Q32 42 36 38"/><rect fill="%23ff6b35" x="14" y="50" width="8" height="12" rx="2"/><rect fill="%23ff6b35" x="42" y="50" width="8" height="12" rx="2"/></svg>')}")`,
  },
  eagle: {
    label: "ОРЁЛ",
    shell: "linear-gradient(145deg, #54a0ff 0%, #2e86de 50%, #54a0ff 100%)",
    shellGlow: "rgba(84,160,255,0.4)",
    heartEmoji: "💙",
    sprite: `url("data:image/svg+xml,${encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><ellipse fill="%234a69bd" cx="32" cy="36" rx="14" ry="12"/><ellipse fill="%23f5f6fa" cx="32" cy="28" rx="12" ry="10"/><path fill="%23f0932b" d="M28 26 L32 30 L36 26 Z"/><circle fill="%232c3e50" cx="28" cy="26" r="2"/><circle fill="%232c3e50" cx="36" cy="26" r="2"/><path fill="%234a69bd" d="M18 32 Q12 28 14 36 Q16 40 20 38"/><path fill="%234a69bd" d="M46 32 Q52 28 50 36 Q48 40 44 38"/><rect fill="%23f0932b" x="28" y="46" width="4" height="10" rx="1"/><rect fill="%23f0932b" x="32" y="46" width="4" height="10" rx="1"/></svg>')}")`,
  },
};

const BAR_COLORS = {
  hunger: "linear-gradient(90deg, #e74c3c, #f39c12)",
  happiness: "linear-gradient(90deg, #f39c12, #f1c40f)",
  energy: "linear-gradient(90deg, #3498db, #2ecc71)",
};

export function TamagotchiWidget({
  pet,
  hunger = 80,
  happiness = 65,
  energy = 90,
  compact = false,
}: Props) {
  const cfg = PET_CONFIG[pet];

  return (
    <div
      style={{
        background: cfg.shell,
        padding: compact ? "12px 10px 16px" : "16px 14px 20px",
        boxShadow: `0 8px 24px rgba(0,0,0,0.3), inset 0 2px 8px rgba(255,255,255,0.25), inset 0 -2px 8px rgba(0,0,0,0.15), 0 0 20px ${cfg.shellGlow}`,
        borderRadius: "60px 60px 48px 48px",
        position: "relative" as const,
      }}
    >
      {/* Keychain hole */}
      <div
        style={{
          position: "absolute",
          top: -6,
          left: "50%",
          transform: "translateX(-50%)",
          width: 16,
          height: 16,
          background: "#1a1a2e",
          borderRadius: "50%",
          boxShadow: "inset 0 1px 3px rgba(0,0,0,0.5)",
        }}
      />

      {/* Screen */}
      <div
        style={{
          background: "#2d3436",
          borderRadius: 12,
          padding: 8,
          marginBottom: compact ? 8 : 12,
          boxShadow: "inset 0 2px 8px rgba(0,0,0,0.5)",
        }}
      >
        <div
          style={{
            width: "100%",
            height: compact ? 80 : 100,
            background: "linear-gradient(180deg, #98ddca 0%, #c7f5ba 60%, #8bc34a 60%, #689f38 100%)",
            borderRadius: 6,
            position: "relative",
            overflow: "hidden",
            imageRendering: "pixelated",
          }}
        >
          {/* Sun */}
          <motion.div
            animate={{ scale: [1, 1.1, 1] }}
            transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
            style={{
              position: "absolute",
              top: 6,
              left: 8,
              width: 16,
              height: 16,
              background: "#ffd93d",
              borderRadius: "50%",
              boxShadow: "0 0 10px #ffd93d, 0 0 20px #ffd93d",
            }}
          />

          {/* Pet sprite */}
          <motion.div
            animate={{ y: [0, -3, 0] }}
            transition={{ duration: 1, repeat: Infinity, ease: "easeInOut" }}
            style={{
              position: "absolute",
              bottom: pet === "eagle" ? 20 : 12,
              left: "50%",
              transform: "translateX(-50%)",
              width: compact ? 36 : 44,
              height: compact ? 36 : 44,
              backgroundImage: cfg.sprite,
              backgroundSize: "contain",
              backgroundRepeat: "no-repeat",
              imageRendering: "pixelated",
            }}
          />

          {/* Screen reflection */}
          <div
            style={{
              position: "absolute",
              top: 3,
              right: 6,
              width: 30,
              height: 14,
              background: "linear-gradient(135deg, rgba(255,255,255,0.35) 0%, transparent 100%)",
              borderRadius: "50%",
              transform: "rotate(-20deg)",
              pointerEvents: "none",
            }}
          />
        </div>
      </div>

      {/* Status bars */}
      <div style={{ display: "flex", flexDirection: "column", gap: compact ? 4 : 6, marginBottom: compact ? 6 : 10 }}>
        {([
          { label: "ЕДА", value: hunger, gradient: BAR_COLORS.hunger },
          { label: "ФАН", value: happiness, gradient: BAR_COLORS.happiness },
          { label: "СИЛ", value: energy, gradient: BAR_COLORS.energy },
        ] as const).map((bar) => (
          <div key={bar.label} style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span
              className="font-pixel"
              style={{
                fontSize: 7,
                color: "#fff",
                width: 28,
                textShadow: "0 1px 2px rgba(0,0,0,0.3)",
                flexShrink: 0,
              }}
            >
              {bar.label}
            </span>
            <div
              style={{
                flex: 1,
                height: 6,
                background: "rgba(0,0,0,0.3)",
                borderRadius: 3,
                overflow: "hidden",
                boxShadow: "inset 0 1px 2px rgba(0,0,0,0.3)",
              }}
            >
              <motion.div
                initial={{ width: 0 }}
                animate={{ width: `${bar.value}%` }}
                transition={{ duration: 0.6, ease: "easeOut" }}
                style={{
                  height: "100%",
                  borderRadius: 3,
                  background: bar.gradient,
                  boxShadow: "0 0 4px rgba(255,255,255,0.2)",
                }}
              />
            </div>
          </div>
        ))}
      </div>

      {/* Pet name */}
      <div
        className="font-pixel"
        style={{
          textAlign: "center",
          color: "rgba(255,255,255,0.85)",
          fontSize: 8,
          letterSpacing: 2,
          textShadow: "0 1px 3px rgba(0,0,0,0.3)",
        }}
      >
        {cfg.label}
      </div>
    </div>
  );
}

export const MODE_TO_PET: Record<string, TamagotchiPet> = {
  free_dialog: "lion",
  blitz: "tiger",
  themed: "eagle",
};
