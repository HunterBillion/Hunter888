/**
 * telemetry — minimal stub for client-side analytics events.
 *
 * 2026-04-23 Sprint 3 (Zone 3 of plan moonlit-baking-crane.md).
 *
 * For now, dispatched events are just `console.log`'d in dev. In
 * production they go nowhere (silenced). When we wire a real backend
 * collector (e.g. /analytics/events), only this file changes — call
 * sites stay the same.
 *
 * Event catalog (used by ScriptPanel + ScriptDrawer + RetrainWidget):
 *
 *   script_panel_toggle    {stage: number, open: boolean}
 *   script_example_copied  {stage: number, example_idx: number}
 *   script_drawer_auto_open {stage: number, trigger: "stage_update" | "stage_skipped"}
 *   stage_skipped          {missed: number, current: number}
 *   whisper_script_clicked {stage: number}
 *   retrain_widget_shown   {mode: "call" | "chat", from_session: string}
 *   retrain_widget_clicked {mode: "call" | "chat", from_session: string}
 */

type EventName =
  | "script_panel_toggle"
  | "script_example_copied"
  | "script_drawer_auto_open"
  | "stage_skipped"
  | "whisper_script_clicked"
  | "retrain_widget_shown"
  | "retrain_widget_clicked";

const isDev =
  typeof process !== "undefined" && process.env?.NODE_ENV === "development";

export const telemetry = {
  track(event: EventName, payload?: Record<string, unknown>): void {
    if (isDev) {
      // Direct console.log so devs can see events without enabling logger.
      // eslint-disable-next-line no-console
      console.log(`[telemetry] ${event}`, payload || {});
    }
    // TODO: when collector exists, POST { event, payload, ts }
    //       to /api/analytics/events here. Fire-and-forget, no await.
  },
};
