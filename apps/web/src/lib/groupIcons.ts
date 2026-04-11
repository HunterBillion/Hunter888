import type { Icon as PhosphorIcon } from "@phosphor-icons/react";
import {
  ShieldWarning, HeartHalf, Crown, Ghost, Sparkle,
  Brain, UsersThree, Clock, Briefcase, Atom,
} from "@phosphor-icons/react";

/**
 * Maps ARCHETYPE_GROUPS icon keys to Phosphor icons.
 * Rendered with weight="duotone" in components.
 */
export const GROUP_ICONS: Record<string, PhosphorIcon> = {
  "shield-alert": ShieldWarning,
  "heart-pulse": HeartHalf,
  "crown": Crown,
  "ghost": Ghost,
  "sparkles": Sparkle,
  "brain": Brain,
  "users": UsersThree,
  "clock": Clock,
  "briefcase": Briefcase,
  "atom": Atom,
};
