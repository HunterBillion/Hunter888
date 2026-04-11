"use client";

import type { Icon as PhosphorIcon } from "@phosphor-icons/react";
import {
  Shield, Heart, Crown, Wind, Star, Brain, Users, Hourglass,
  Briefcase, Sparkle, Target, Trophy, Flame, Lightning, Lock,
  Warning, CheckCircle, XCircle, Question, Info,
  Sword, Medal, MedalMilitary, TrendUp, TrendDown,
  Skull, Circle, Crosshair, Eye, EyeClosed,
  ThumbsUp, ThumbsDown, ChatCircle, Phone, Envelope,
  CurrencyDollar, CreditCard, Buildings, House, Car,
  Stethoscope, GraduationCap, Scales, Gavel, Newspaper,
  Monitor, Gear, User, UserCheck, UserMinus,
  ClipboardText, Plant, ChartBar, Robot, CastleTurret,
  WifiHigh, Handshake, Alarm, Fish,
  GraduationCap as Wheat, Truck, ShoppingCart, Barbell, Palette,
  Microscope, Bank, SealCheck, HardHat, Wrench,
  SmileyMeh, SmileyNervous, SmileyAngry, HandHeart, Moon, Timer, Smiley,
} from "@phosphor-icons/react";

/** Maps emoji characters to Phosphor icons (rendered as duotone) */
const EMOJI_TO_ICON: Record<string, PhosphorIcon> = {
  // Groups
  "🛡️": Shield, "🛡": Shield,
  "💜": Heart,
  "👑": Crown,
  "🌫️": Wind, "🌫": Wind, "🌬️": Wind, "🌬": Wind,
  "⭐": Star,
  "🧠": Brain,
  "👥": Users,
  "⏳": Hourglass,
  "💼": Briefcase,
  "🔮": Sparkle,
  // Actions/States
  "🎯": Target,
  "🏆": Trophy,
  "🔥": Flame,
  "⚡": Lightning,
  "🔒": Lock,
  "⚠️": Warning, "⚠": Warning,
  "✅": CheckCircle,
  "❌": XCircle,
  "❓": Question,
  "ℹ️": Info,
  "⚔️": Sword, "⚔": Sword,
  "🥇": Medal,
  "🥈": Medal,
  "🥉": Medal,
  "🏅": MedalMilitary,
  "📈": TrendUp,
  "📉": TrendDown,
  "💀": Skull,
  "🟢": Circle,
  "🟡": Circle,
  "🔴": Circle,
  "👁": Eye,
  "👍": ThumbsUp,
  "👎": ThumbsDown,
  "💬": ChatCircle,
  "📞": Phone,
  "📧": Envelope,
  "💰": CurrencyDollar,
  "💳": CreditCard,
  "🏢": Buildings,
  "🏠": House,
  "🚗": Car,
  "🏥": Stethoscope,
  "🎓": GraduationCap,
  "⚖️": Scales, "⚖": Scales,
  "🔨": Gavel,
  "📰": Newspaper,
  "💻": Monitor,
  "⚙️": Gear, "⚙": Gear,
  "👤": User,
  "✓": CheckCircle,
  "❄️": Sparkle, "❄": Sparkle,
  "📋": ClipboardText,
  "🌱": Plant,
  "📊": ChartBar,
  "🤖": Robot,
  "🏰": CastleTurret,
  "📶": WifiHigh,
  "🤝": Handshake,
  "⏰": Alarm,
  "🐟": Fish,
  "💡": Sparkle,
  // Professions
  "🏛️": Bank, "🏛": Bank,
  "🎖️": SealCheck, "🎖": SealCheck,
  "👮": SealCheck,
  "📚": GraduationCap,
  "💹": TrendUp,
  "🔧": Wrench,
  "🏗️": HardHat, "🏗": HardHat,
  "🚚": Truck,
  "🌾": Wheat,
  "🔬": Microscope,
  "🎨": Palette,
  "🛒": ShoppingCart,
  "👴": User,
  "🎒": GraduationCap,
  // Family
  "👨‍👩‍👧": Users,
  "👨‍👩‍👧‍👦": Users,
  // Moods
  "😐": SmileyMeh,
  "😰": SmileyNervous,
  "😠": SmileyAngry,
  "🤞": HandHeart,
  "😴": Moon,
  "😁": Smiley,
};

interface AppIconProps {
  emoji: string;
  size?: number;
  className?: string;
  style?: React.CSSProperties;
}

/**
 * Renders emoji as a Phosphor duotone icon. Consistent on all platforms.
 * Falls back to the emoji character if no mapping exists.
 */
export function AppIcon({ emoji, size = 18, className = "", style }: AppIconProps) {
  const IconComponent = EMOJI_TO_ICON[emoji];
  if (IconComponent) {
    return <IconComponent size={size} weight="duotone" className={className} style={style} />;
  }
  // Fallback: render raw emoji with consistent sizing
  return (
    <span className={`inline-flex items-center justify-center ${className}`} style={{ width: size, height: size, fontSize: size * 0.8, lineHeight: 1, ...style }}>
      {emoji}
    </span>
  );
}

export { EMOJI_TO_ICON };
