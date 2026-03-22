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

type TypeFilter = "all" | "cold" | "warm" | "objection" | "in" | "upsell" | "rescue" | "couple_call" | "vip_debtor";
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
      set({ scenarios: data, scenariosLoading: false });
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
      // Type filter
      if (typeFilter !== "all") {
        const typePrefix = s.scenario_type.split("_")[0];
        if (typeFilter === "cold" && !s.scenario_type.startsWith("cold")) return false;
        if (typeFilter === "warm" && !s.scenario_type.startsWith("warm")) return false;
        if (typeFilter === "objection" && typePrefix !== "objection") return false;
        if (typeFilter === "in" && !s.scenario_type.startsWith("in_")) return false;
        if (!["cold", "warm", "objection", "in", "all"].includes(typeFilter)) {
          if (s.scenario_type !== typeFilter) return false;
        }
      }
      // Difficulty filter
      if (difficultyFilter === "easy" && s.difficulty > 3) return false;
      if (difficultyFilter === "medium" && (s.difficulty < 4 || s.difficulty > 6)) return false;
      if (difficultyFilter === "hard" && s.difficulty < 7) return false;
      return true;
    });
  },
}));
