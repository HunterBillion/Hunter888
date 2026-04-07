import { create } from "zustand";
import { api } from "@/lib/api";
import type { Scenario } from "@/types";

interface AssignedTraining {
  id: string;
  scenario_id: string;
  scenario_title: string;
  assigned_by: string;
  deadline: string;
  created_at: string;
}

interface SavedCharacter {
  id: string;
  name: string;
  archetype: string;
  profession: string;
  lead_source: string;
  difficulty: number;
  created_at: string;
}

type TypeFilter = "all" | "cold" | "warm" | "in" | "special" | "follow_up" | "crisis" | "compliance" | "multi_party";
type DifficultyFilter = "all" | "easy" | "medium" | "hard";

interface TrainingState {
  // Scenarios
  scenarios: Scenario[];
  scenariosLoading: boolean;

  // Filters
  typeFilter: TypeFilter;
  difficultyFilter: DifficultyFilter;

  // Assigned
  assigned: AssignedTraining[];
  assignedLoading: boolean;

  // Saved characters
  savedCharacters: SavedCharacter[];
  savedLoading: boolean;

  // Actions
  fetchScenarios: () => Promise<void>;
  fetchAssigned: () => Promise<void>;
  fetchSavedCharacters: () => Promise<void>;
  setTypeFilter: (filter: TypeFilter) => void;
  setDifficultyFilter: (filter: DifficultyFilter) => void;

  // Computed
  filteredScenarios: () => Scenario[];
}

export const useTrainingStore = create<TrainingState>((set, get) => ({
  scenarios: [],
  scenariosLoading: false,
  typeFilter: "all",
  difficultyFilter: "all",
  assigned: [],
  assignedLoading: false,
  savedCharacters: [],
  savedLoading: false,

  fetchScenarios: async () => {
    set({ scenariosLoading: true });
    try {
      const data = await api.get("/scenarios/");
      // Validate response is array (#17) — prevents map() crash in consuming components
      set({ scenarios: Array.isArray(data) ? data : [], scenariosLoading: false });
    } catch {
      set({ scenariosLoading: false });
    }
  },

  fetchAssigned: async () => {
    set({ assignedLoading: true });
    try {
      const data = await api.get("/training/assigned");
      set({ assigned: Array.isArray(data) ? data : [], assignedLoading: false });
    } catch {
      set({ assignedLoading: false });
    }
  },

  fetchSavedCharacters: async () => {
    set({ savedLoading: true });
    try {
      const data = await api.get("/characters/custom");
      set({ savedCharacters: Array.isArray(data) ? data : [], savedLoading: false });
    } catch {
      set({ savedLoading: false });
    }
  },

  setTypeFilter: (typeFilter) => set({ typeFilter }),
  setDifficultyFilter: (difficultyFilter) => set({ difficultyFilter }),

  filteredScenarios: () => {
    const { scenarios, typeFilter, difficultyFilter } = get();
    return scenarios.filter((s) => {
      // Type filter — 8 scenario groups (DOC_05)
      // Supports both new codes (cold_first_contact, follow_up_check_in, etc.)
      // and legacy enum values (cold_call, warm_call, objection_handling, consultation)
      if (typeFilter !== "all") {
        const sType = s.scenario_type || "";
        if (typeFilter === "cold" && !sType.startsWith("cold")) return false;
        if (typeFilter === "warm" && !(sType.startsWith("warm") || sType === "consultation")) return false;
        if (typeFilter === "in" && !sType.startsWith("in_")) return false;
        if (typeFilter === "special" && !(["special_", "upsell", "rescue", "vip_debtor"].some((p) => sType.startsWith(p)) || sType === "objection_handling")) return false;
        if (typeFilter === "follow_up" && !sType.startsWith("follow_up")) return false;
        if (typeFilter === "crisis" && !sType.startsWith("crisis")) return false;
        if (typeFilter === "compliance" && !sType.startsWith("compliance")) return false;
        if (typeFilter === "multi_party" && !sType.startsWith("multi_party")) return false;
      }
      // Difficulty filter
      if (difficultyFilter === "easy" && s.difficulty > 3) return false;
      if (difficultyFilter === "medium" && (s.difficulty < 4 || s.difficulty > 6)) return false;
      if (difficultyFilter === "hard" && s.difficulty < 7) return false;
      return true;
    });
  },
}));
