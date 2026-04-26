"use client";

/**
 * /admin/audit-log — kept as a thin wrapper around <AuditLogPanel> for
 * backwards compat (existing bookmarks, deep links). The same panel is
 * mounted from /dashboard tab "Активность" — see PR-3 (#TBD).
 *
 * /admin will be removed entirely in PR-6, at which point this file
 * goes too. Until then the panel lives in two places.
 */

import { useEffect, useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { isAdmin } from "@/lib/guards";
import { AuditLogPanel } from "@/components/dashboard/AuditLogPanel";

export default function AdminAuditLogPage() {
  const { user } = useAuth();
  const [denied, setDenied] = useState(false);

  useEffect(() => {
    if (user && !isAdmin(user)) setDenied(true);
  }, [user]);

  if (denied) {
    return (
      <div className="glass-panel rounded-xl" style={{ padding: 24, textAlign: "center", color: "var(--danger)" }}>
        Доступ ограничен. Только для администраторов.
      </div>
    );
  }

  return <AuditLogPanel scope="all" />;
}
