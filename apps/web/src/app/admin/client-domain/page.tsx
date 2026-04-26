"use client";

/**
 * Thin re-export — the panel itself lives in
 * components/dashboard/ClientDomainPanel.tsx and is also mounted from
 * /dashboard "Система" tab. Admin gate is handled by /admin/layout.tsx.
 *
 * /admin will be removed in PR-6, at which point this file goes too.
 */

export { ClientDomainPanel as default } from "@/components/dashboard/ClientDomainPanel";
