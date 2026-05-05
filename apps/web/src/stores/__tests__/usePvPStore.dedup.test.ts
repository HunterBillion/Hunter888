/**
 * Regression test: PvP message dedup via client_msg_id / server_msg_id.
 *
 * Bug reproduced on prod (duel 02bd9a42, 2026-05-05): every user message
 * rendered twice — once optimistically when the FE sent it, once when the
 * WS echo arrived. Cause was in the duel page WS handler (case
 * "duel.message"), which dropped the ``client_msg_id`` and ``server_msg_id``
 * fields from the echo payload before calling ``addMessage``. Without
 * those, the dedup logic in ``addMessage`` could not match the optimistic
 * pending row → fell through to append, producing the double bubble.
 *
 * The store-level reconcile rules (Issue #167) are correct; only the
 * call-site forwarding was wrong. This test pins the rules so a future
 * refactor cannot silently regress them.
 */

import { describe, it, expect, beforeEach } from "vitest";
import { usePvPStore } from "../usePvPStore";

const baseMsg = (over: Partial<Parameters<typeof usePvPStore.getState.prototype>[0]> = {}) => ({
  id: "init",
  sender_role: "seller" as const,
  text: "начнем",
  round: 1,
  timestamp: "2026-05-05T15:25:00Z",
  ...over,
});

describe("usePvPStore.addMessage dedup", () => {
  beforeEach(() => {
    usePvPStore.getState().resetDuel();
  });

  it("upgrades optimistic pending row when echo carries the same client_msg_id", () => {
    const cid = "pvp-client-1";
    // Optimistic bubble — FE adds before sendMessage().
    usePvPStore.getState().addMessage({
      id: cid,
      sender_role: "seller",
      text: "начнем",
      round: 1,
      timestamp: "2026-05-05T15:25:00Z",
      client_msg_id: cid,
      pending: true,
    });
    expect(usePvPStore.getState().messages).toHaveLength(1);
    expect(usePvPStore.getState().messages[0].pending).toBe(true);

    // Server echo — same client_msg_id + a fresh server_msg_id.
    usePvPStore.getState().addMessage({
      id: "ignored-fresh",
      sender_role: "seller",
      text: "начнем",
      round: 1,
      timestamp: "2026-05-05T15:25:01Z",
      client_msg_id: cid,
      server_msg_id: "srv-abc",
    });

    const msgs = usePvPStore.getState().messages;
    expect(msgs).toHaveLength(1);
    expect(msgs[0].pending).toBe(false);
    expect(msgs[0].server_msg_id).toBe("srv-abc");
  });

  it("appends when echo arrives WITHOUT client_msg_id (the prod bug)", () => {
    // This is what the PRE-FIX duel page handler produced: it dropped
    // ``client_msg_id`` from the payload, so the echo looked like a brand
    // new message. The store has no choice but to append → double bubble.
    const cid = "pvp-client-2";
    usePvPStore.getState().addMessage({
      id: cid,
      sender_role: "seller",
      text: "начнем",
      round: 1,
      timestamp: "2026-05-05T15:25:00Z",
      client_msg_id: cid,
      pending: true,
    });
    usePvPStore.getState().addMessage({
      id: "fresh-2",
      sender_role: "seller",
      text: "начнем",
      round: 1,
      timestamp: "2026-05-05T15:25:01Z",
      // NO client_msg_id forwarded → cannot match the optimistic row.
    });

    expect(usePvPStore.getState().messages).toHaveLength(2);
  });

  it("drops duplicate echo by server_msg_id (reconnect-resume race)", () => {
    usePvPStore.getState().addMessage({
      id: "msg-x",
      sender_role: "client",
      text: "Алло",
      round: 1,
      timestamp: "2026-05-05T15:25:00Z",
      server_msg_id: "srv-x",
    });
    usePvPStore.getState().addMessage({
      id: "msg-x-dup",
      sender_role: "client",
      text: "Алло",
      round: 1,
      timestamp: "2026-05-05T15:25:00Z",
      server_msg_id: "srv-x",
    });
    expect(usePvPStore.getState().messages).toHaveLength(1);
  });

  it("appends opponent (no client_msg_id) messages without affecting the user's pending row", () => {
    const cid = "pvp-client-3";
    usePvPStore.getState().addMessage({
      id: cid,
      sender_role: "seller",
      text: "начнем",
      round: 1,
      timestamp: "2026-05-05T15:25:00Z",
      client_msg_id: cid,
      pending: true,
    });
    // Bot reply — no client_msg_id; should append, not match the seller row.
    usePvPStore.getState().addMessage({
      id: "bot-1",
      sender_role: "client",
      text: "Алло, слушаю...",
      round: 1,
      timestamp: "2026-05-05T15:25:02Z",
      server_msg_id: "srv-bot-1",
    });
    expect(usePvPStore.getState().messages).toHaveLength(2);
    expect(usePvPStore.getState().messages[0].pending).toBe(true);
    expect(usePvPStore.getState().messages[1].sender_role).toBe("client");
  });
});
