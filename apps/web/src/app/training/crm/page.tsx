import { redirect } from "next/navigation";

/**
 * Backward-compat redirect: /training/crm → /stories
 *
 * 2026-04-18: "Игровая CRM" was renamed to "AI-Портфель" (URL /stories) to
 * avoid user confusion with the real business CRM at /clients. Old bookmarks
 * and cached links land here; this server-side redirect sends them on.
 */
export default function TrainingCrmRedirect() {
  redirect("/stories");
}
