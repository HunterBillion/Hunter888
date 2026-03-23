"use client";

import { useEffect } from "react";
import { useParams, useRouter } from "next/navigation";

export default function KnowledgeSessionRedirect() {
  const router = useRouter();
  const { sessionId } = useParams<{ sessionId: string }>();
  useEffect(() => {
    router.replace(`/pvp/quiz/${sessionId}`);
  }, [router, sessionId]);
  return null;
}
