"use client";

import {
  Shield, Heart, Crown, Wind, Star, Brain, Users, Clock,
  Briefcase, Sparkles, Target, Trophy, Flame, Zap, Lock,
  AlertTriangle, CheckCircle, XCircle, HelpCircle, Info,
  Swords, Medal, Award, TrendingUp, TrendingDown,
  Skull, CircleDot, Crosshair, Eye, EyeOff,
  ThumbsUp, ThumbsDown, MessageSquare, Phone, Mail,
  DollarSign, CreditCard, Building, Home, Car,
  Stethoscope, GraduationCap, Scale, Gavel, Newspaper,
  Monitor, Settings, User, UserCheck, UserX,
  ClipboardList, Sprout, BarChart3, Bot, Castle,
  Signal, Handshake, AlarmClock, Fish,
  type LucideIcon,
} from "lucide-react";

/** Maps emoji characters to Lucide icons */
const EMOJI_TO_ICON: Record<string, LucideIcon> = {
  // Groups
  "🛡️": Shield, "🛡": Shield,
  "💜": Heart,
  "👑": Crown,
  "🌫️": Wind, "🌫": Wind, "🌬️": Wind, "🌬": Wind,
  "⭐": Star,
  "🧠": Brain,
  "👥": Users,
  "⏳": Clock,
  "💼": Briefcase,
  "🔮": Sparkles,
  // Actions/States
  "🎯": Target,
  "🏆": Trophy,
  "🔥": Flame,
  "⚡": Zap,
  "🔒": Lock,
  "⚠️": AlertTriangle, "⚠": AlertTriangle,
  "✅": CheckCircle,
  "❌": XCircle,
  "❓": HelpCircle,
  "ℹ️": Info,
  "⚔️": Swords, "⚔": Swords,
  "🥇": Medal,
  "🥈": Medal,
  "🥉": Medal,
  "🏅": Award,
  "📈": TrendingUp,
  "📉": TrendingDown,
  "💀": Skull,
  "🟢": CircleDot,
  "🟡": CircleDot,
  "🔴": CircleDot,
  "👁": Eye,
  "👍": ThumbsUp,
  "👎": ThumbsDown,
  "💬": MessageSquare,
  "📞": Phone,
  "📧": Mail,
  "💰": DollarSign,
  "💳": CreditCard,
  "🏢": Building,
  "🏠": Home,
  "🚗": Car,
  "🏥": Stethoscope,
  "🎓": GraduationCap,
  "⚖️": Scale, "⚖": Scale,
  "🔨": Gavel,
  "📰": Newspaper,
  "💻": Monitor,
  "⚙️": Settings, "⚙": Settings,
  "👤": User,
  "✓": CheckCircle,
  "❄️": Sparkles, "❄": Sparkles,
  "📋": ClipboardList,
  "🌱": Sprout,
  "📊": BarChart3,
  "🤖": Bot,
  "🏰": Castle,
  "📶": Signal,
  "🤝": Handshake,
  "⏰": AlarmClock,
  "🐟": Fish,
  "💡": Sparkles,
  // Fallback handled in component
};

interface AppIconProps {
  emoji: string;
  size?: number;
  className?: string;
  style?: React.CSSProperties;
}

/**
 * Renders emoji as a Lucide icon. Consistent on all platforms.
 * Falls back to the emoji character if no mapping exists.
 */
export function AppIcon({ emoji, size = 18, className = "", style }: AppIconProps) {
  const Icon = EMOJI_TO_ICON[emoji];
  if (Icon) {
    return <Icon size={size} className={className} style={style} />;
  }
  // Fallback: render raw emoji with consistent sizing
  return (
    <span className={`inline-flex items-center justify-center ${className}`} style={{ width: size, height: size, fontSize: size * 0.8, lineHeight: 1, ...style }}>
      {emoji}
    </span>
  );
}

export { EMOJI_TO_ICON };
