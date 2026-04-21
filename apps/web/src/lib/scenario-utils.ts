import type { ScenarioGroup } from "@/types";

export interface ScenarioTypeConfig {
  label: string;
  color: string;
  bg: string;
  border: string;
  group: ScenarioGroup;
}

const GROUP_CONFIGS: Record<ScenarioGroup, Omit<ScenarioTypeConfig, "group"> & { group: ScenarioGroup }> = {
  cold:       { label: "Холодный",    color: "var(--info)", bg: "var(--info-muted)",  border: "color-mix(in srgb, var(--info) 25%, transparent)", group: "cold" },
  warm:       { label: "Тёплый",      color: "var(--warning)", bg: "var(--warning-muted)",  border: "color-mix(in srgb, var(--warning) 25%, transparent)", group: "warm" },
  inbound:    { label: "Входящий",    color: "var(--success)", bg: "var(--success-muted)",   border: "color-mix(in srgb, var(--success) 25%, transparent)",  group: "inbound" },
  special:    { label: "Особый",      color: "var(--magenta)", bg: "color-mix(in srgb, var(--magenta) 10%, transparent)",  border: "color-mix(in srgb, var(--magenta) 25%, transparent)", group: "special" },
  follow_up:  { label: "Follow-up",   color: "var(--accent)", bg: "var(--accent-muted)",  border: "var(--accent-glow)", group: "follow_up" },
  crisis:     { label: "Кризис",      color: "var(--danger)", bg: "var(--danger-muted)",   border: "color-mix(in srgb, var(--danger) 25%, transparent)",  group: "crisis" },
  compliance: { label: "Комплаенс",   color: "var(--text-muted)", bg: "color-mix(in srgb, var(--text-muted) 10%, transparent)", border: "color-mix(in srgb, var(--text-muted) 25%, transparent)", group: "compliance" },
  multi_party:{ label: "Мультипарти", color: "var(--magenta)", bg: "color-mix(in srgb, var(--magenta) 10%, transparent)",  border: "color-mix(in srgb, var(--magenta) 25%, transparent)", group: "multi_party" },
};

export function getScenarioTypeConfig(scenarioType: string): ScenarioTypeConfig {
  if (scenarioType.startsWith("cold"))        return GROUP_CONFIGS.cold;
  if (scenarioType.startsWith("warm"))        return GROUP_CONFIGS.warm;
  if (scenarioType.startsWith("in_"))         return GROUP_CONFIGS.inbound;
  if (scenarioType.startsWith("follow_up"))   return GROUP_CONFIGS.follow_up;
  if (scenarioType.startsWith("crisis"))      return GROUP_CONFIGS.crisis;
  if (scenarioType.startsWith("compliance"))  return GROUP_CONFIGS.compliance;
  if (scenarioType.startsWith("multi_party")) return GROUP_CONFIGS.multi_party;
  // special, upsell, rescue, vip_debtor
  return GROUP_CONFIGS.special;
}

export function getScenarioGroupLabel(group: ScenarioGroup): string {
  return GROUP_CONFIGS[group]?.label ?? group;
}

export { GROUP_CONFIGS as SCENARIO_GROUP_CONFIGS };
