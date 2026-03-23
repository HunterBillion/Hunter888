"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function KnowledgeRedirect() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/pvp");
  }, [router]);
  return null;
}
