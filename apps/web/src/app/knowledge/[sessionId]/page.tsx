"use client";

import { useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";

export default function KnowledgeSessionRedirect() {
  const router = useRouter();
  const { sessionId } = useParams<{ sessionId: string }>();
  useEffect(() => {
    router.replace(`/pvp/quiz/${sessionId}`);
  }, [router, sessionId]);
  return (
    <div className="flex min-h-screen items-center justify-center" style={{ background: "var(--bg-primary)" }}>
      <Loader2 size={24} className="animate-spin" style={{ color: "var(--accent)" }} />
    </div>
  );
}
