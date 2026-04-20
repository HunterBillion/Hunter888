"use client";

/**
 * CallButton — entry-point into the live-call (phone) mode.
 *
 * Phase 2.10 (2026-04-19). Renders a compact "Live call" control in the
 * training chat header. Clicking it navigates to `/training/[id]/call`
 * where the full-screen PhoneCallMode takes over.
 *
 * Visibility gate: only shown for scenarios with difficulty >= 4 (set via
 * `VOICE_MODE_ENABLED_FROM_DIFFICULTY` in the design plan). Easier
 * scenarios stay chat-only to keep the learning curve gentle.
 */

import { useRouter } from "next/navigation";
import { Phone } from "lucide-react";

interface Props {
  /** Training session id — destination is `/training/<id>/call`. */
  sessionId: string;
  /** Current scenario difficulty. Call mode is gated at >= 4. */
  difficulty: number;
  /** Disable while WS reconnecting or session not ready. */
  disabled?: boolean;
}

export function CallButton({ sessionId, difficulty, disabled }: Props) {
  const router = useRouter();
  if (difficulty < 4) return null;

  return (
    <button
      type="button"
      disabled={disabled}
      onClick={() => router.push(`/training/${sessionId}/call`)}
      className="flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm font-medium transition-all disabled:opacity-40"
      style={{
        background: "var(--accent-muted)",
        color: "var(--accent)",
        border: "1px solid var(--accent)",
      }}
      title="Переключиться в режим живого звонка"
    >
      <Phone size={15} />
      <span>Живой звонок</span>
    </button>
  );
}
