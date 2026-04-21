"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/**
 * /results — index route stub.
 *
 * Journal #112 (class N — Next.js quirks): Next.js App Router with only
 * /results/[id]/page.tsx (no parent /results/page.tsx) generates a 404
 * whenever the router prefetches the parent segment (via <Link> hover,
 * viewport proximity, or RSC navigation). The error is cosmetic — it
 * never reaches the user as a broken page — but it clutters the console
 * and makes real errors harder to spot.
 *
 * Rather than deep-linking this route, we redirect to /history which
 * already renders the list of past sessions.
 */
export default function ResultsIndexPage() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/history");
  }, [router]);
  return null;
}
