"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Trophy, Star, Flame, Shield, Crown, Award, Zap, BookOpen, Sword, GraduationCap } from "lucide-react";

interface AchievementNotification {
  slug: string;
  title: string;
  description: string;
  icon: string;
  rarity: string;
  xp_bonus: number;
}

const RARITY_COLORS: Record<string, string> = {
  common: "#8B95A5",
  rare: "#5B9FE5",
  epic: "#818CF8",
  legendary: "#F59E0B",
};

const ICON_MAP: Record<string, React.ElementType> = {
  swords: Sword,
  "book-open": BookOpen,
  zap: Zap,
  sword: Sword,
  shield: Shield,
  award: Award,
  chess: Trophy,
  crown: Crown,
  flame: Flame,
  "graduation-cap": GraduationCap,
  star: Star,
  trophy: Trophy,
};

export function AchievementToast({
  achievement,
  onDismiss,
}: {
  achievement: AchievementNotification;
  onDismiss: () => void;
}) {
  const [visible, setVisible] = useState(true);
  const color = RARITY_COLORS[achievement.rarity] || RARITY_COLORS.common;
  const IconComponent = (ICON_MAP as Record<string, typeof Trophy>)[achievement.icon] || Trophy;

  useEffect(() => {
    const timer = setTimeout(() => {
      setVisible(false);
      setTimeout(onDismiss, 300);
    }, 5000);
    return () => clearTimeout(timer);
  }, [onDismiss]);

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          initial={{ opacity: 0, y: -50, scale: 0.9 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: -30, scale: 0.9 }}
          transition={{ type: "spring", damping: 20, stiffness: 300 }}
          className="fixed top-4 right-4 z-[9999] max-w-sm cursor-pointer"
          onClick={() => {
            setVisible(false);
            setTimeout(onDismiss, 300);
          }}
        >
          <div
            className="rounded-2xl p-4 shadow-2xl backdrop-blur-xl"
            style={{
              background: `linear-gradient(135deg, ${color}15, ${color}08)`,
              border: `1px solid ${color}40`,
              boxShadow: `0 0 30px ${color}20, 0 8px 32px rgba(0,0,0,0.3)`,
            }}
          >
            <div className="flex items-center gap-3">
              <div
                className="flex h-12 w-12 items-center justify-center rounded-xl"
                style={{
                  background: `${color}20`,
                  border: `1px solid ${color}40`,
                }}
              >
                <IconComponent size={24} style={{ color }} />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span
                    className="font-mono text-xs uppercase tracking-widest"
                    style={{ color }}
                  >
                    {achievement.rarity}
                  </span>
                </div>
                <div
                  className="font-display text-sm font-bold truncate"
                  style={{ color: "var(--text-primary)" }}
                >
                  {achievement.title}
                </div>
                <div
                  className="text-xs truncate"
                  style={{ color: "var(--text-muted)" }}
                >
                  {achievement.description}
                </div>
              </div>
              <div
                className="font-display text-lg font-bold"
                style={{ color }}
              >
                +{achievement.xp_bonus}
                <span className="text-xs ml-0.5">XP</span>
              </div>
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}


/**
 * Container for queuing multiple achievement toasts.
 * Use with useKnowledgeStore or WS events.
 */
export function AchievementToastContainer({
  achievements,
  onClear,
}: {
  achievements: AchievementNotification[];
  onClear: () => void;
}) {
  const [queue, setQueue] = useState<AchievementNotification[]>([]);

  useEffect(() => {
    if (achievements.length > 0) {
      setQueue((prev) => [...prev, ...achievements]);
      onClear();
    }
  }, [achievements, onClear]);

  const handleDismiss = () => {
    setQueue((prev) => prev.slice(1));
  };

  if (queue.length === 0) return null;

  return (
    <AchievementToast
      key={queue[0].slug}
      achievement={queue[0]}
      onDismiss={handleDismiss}
    />
  );
}
