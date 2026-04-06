"use client";

import { useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Loader2 } from "lucide-react";
import { Suspense } from "react";

function KnowledgeRedirectInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  useEffect(() => {
    // 3.1: Pass category param through to PvP knowledge tab
    const category = searchParams.get("category");
    if (category) {
      router.replace(`/pvp?tab=knowledge&category=${encodeURIComponent(category)}`);
    } else {
      router.replace("/pvp");
    }
  }, [router, searchParams]);
  return (
    <div className="flex min-h-screen items-center justify-center" style={{ background: "var(--bg-primary)" }}>
      <Loader2 size={24} className="animate-spin" style={{ color: "var(--accent)" }} />
    </div>
  );
}

export default function KnowledgeRedirect() {
  return (
    <Suspense fallback={
      <div className="flex min-h-screen items-center justify-center" style={{ background: "var(--bg-primary)" }}>
        <Loader2 size={24} className="animate-spin" style={{ color: "var(--accent)" }} />
      </div>
    }>
      <KnowledgeRedirectInner />
    </Suspense>
  );
}
