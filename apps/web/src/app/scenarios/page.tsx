/**
 * FIND-016 fix: /scenarios was a 404 (no page.tsx). Some external links and
 * side-navigation entries pointed here. Keep the URL live and redirect to
 * the canonical training archetypes picker where scenarios are chosen.
 */
import { redirect } from "next/navigation";

export default function ScenariosPage() {
  redirect("/training/archetypes");
}
