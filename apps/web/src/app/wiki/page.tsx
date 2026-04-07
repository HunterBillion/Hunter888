"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/**
 * /wiki route is disabled. Wiki is admin-only at /admin/wiki.
 * Redirect any user who visits this URL to /home.
 */
export default function WikiRedirect() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/home");
  }, [router]);
  return null;
}
