/**
 * usePolicyStore — TZ-4 §10 / §13.4.1 client state for the
 * conversation-policy + persona-conflict counters.
 *
 * Wired by ``NotificationWSProvider``: every
 * ``conversation.policy_violation_detected`` / ``persona.conflict_
 * detected`` frame coming over the WS or HTTP-polled outbox bumps
 * the per-session bucket here. Components (``PolicyViolationCounter``,
 * ``PersonaConflictBadge``) read directly from the store keyed by
 * ``sessionId``.
 *
 * The store keeps **per-session** state instead of a global counter
 * so tab-switching between two open sessions doesn't conflate the
 * numbers — a manager running PvP in one tab and a CRM call in
 * another sees each session's audit telemetry separately.
 */
import { create } from "zustand";

export type PolicySeverity = "low" | "medium" | "high" | "critical";

export interface PolicySessionState {
  /** Total counter — sum of all bucketed counts. Convenience read. */
  total: number;
  /** Per-severity counts. Mirrors the backend severity tags. */
  bySeverity: Partial<Record<PolicySeverity, number>>;
  /** Count of ``persona.conflict_detected`` events for this session.
   * The persona badge is conceptually a subset of policy violations
   * (it fires alongside ``persona_conflict`` / ``unjustified_identity_
   * change`` / ``asked_known_slot_again`` codes) but the backend
   * publishes the persona frame separately so the badge can render
   * without parsing every policy frame. */
  personaConflicts: number;
  /** Last attempted-field across this session's persona conflicts.
   * Surfaces in the badge tooltip so the manager doesn't need to
   * open the audit drawer. */
  lastPersonaAttemptedField: string | null;
  /** Whether at least one of the recorded violations was emitted
   * with ``enforce_active=true``. The badge swaps to a louder
   * presentation once enforce mode flips on. */
  enforceActive: boolean;
}

interface PolicyStore {
  bySession: Record<string, PolicySessionState>;
  recordPolicyViolation: (
    sessionId: string,
    severity: PolicySeverity,
    enforceActive?: boolean,
  ) => void;
  recordPersonaConflict: (
    sessionId: string,
    attemptedField?: string | null,
  ) => void;
  /** Reset counters for a session — typically when the manager
   * leaves the session view, or after a manual "clear" action. */
  clearSession: (sessionId: string) => void;
}

const emptyState = (): PolicySessionState => ({
  total: 0,
  bySeverity: {},
  personaConflicts: 0,
  lastPersonaAttemptedField: null,
  enforceActive: false,
});

export const usePolicyStore = create<PolicyStore>((set) => ({
  bySession: {},
  recordPolicyViolation: (sessionId, severity, enforceActive) =>
    set((state) => {
      const prev = state.bySession[sessionId] ?? emptyState();
      const nextSeverity = { ...prev.bySeverity };
      nextSeverity[severity] = (nextSeverity[severity] ?? 0) + 1;
      return {
        bySession: {
          ...state.bySession,
          [sessionId]: {
            ...prev,
            total: prev.total + 1,
            bySeverity: nextSeverity,
            enforceActive: prev.enforceActive || Boolean(enforceActive),
          },
        },
      };
    }),
  recordPersonaConflict: (sessionId, attemptedField) =>
    set((state) => {
      const prev = state.bySession[sessionId] ?? emptyState();
      return {
        bySession: {
          ...state.bySession,
          [sessionId]: {
            ...prev,
            personaConflicts: prev.personaConflicts + 1,
            lastPersonaAttemptedField:
              attemptedField ?? prev.lastPersonaAttemptedField,
          },
        },
      };
    }),
  clearSession: (sessionId) =>
    set((state) => {
      const next = { ...state.bySession };
      delete next[sessionId];
      return { bySession: next };
    }),
}));
