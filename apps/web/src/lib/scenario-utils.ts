import type { ScenarioGroup } from "@/types";

export interface ScenarioTypeConfig {
  label: string;
  color: string;
  bg: string;
  border: string;
  group: ScenarioGroup;
}

const GROUP_CONFIGS: Record<ScenarioGroup, Omit<ScenarioTypeConfig, "group"> & { group: ScenarioGroup }> = {
  cold:       { label: "Холодный",    color: "#3B82F6", bg: "rgba(59,130,246,0.1)",  border: "rgba(59,130,246,0.25)", group: "cold" },
  warm:       { label: "Тёплый",      color: "#F59E0B", bg: "rgba(245,158,11,0.1)",  border: "rgba(245,158,11,0.25)", group: "warm" },
  inbound:    { label: "Входящий",    color: "#22C55E", bg: "rgba(34,197,94,0.1)",   border: "rgba(34,197,94,0.25)",  group: "inbound" },
  special:    { label: "Особый",      color: "#BF55EC", bg: "rgba(191,85,236,0.1)",  border: "rgba(191,85,236,0.25)", group: "special" },
  follow_up:  { label: "Follow-up",   color: "#6366F1", bg: "rgba(99,102,241,0.1)",  border: "rgba(99,102,241,0.25)", group: "follow_up" },
  crisis:     { label: "Кризис",      color: "#EF4444", bg: "rgba(239,68,68,0.1)",   border: "rgba(239,68,68,0.25)",  group: "crisis" },
  compliance: { label: "Комплаенс",   color: "#64748B", bg: "rgba(100,116,139,0.1)", border: "rgba(100,116,139,0.25)", group: "compliance" },
  multi_party:{ label: "Мультипарти", color: "#EC4899", bg: "rgba(236,72,153,0.1)",  border: "rgba(236,72,153,0.25)", group: "multi_party" },
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
