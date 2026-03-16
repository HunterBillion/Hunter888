"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getToken } from "@/lib/auth";
import { api } from "@/lib/api";

export default function Home() {
  const router = useRouter();
  const [status, setStatus] = useState("Загрузка...");

  useEffect(() => {
    const token = getToken();
    if (!token) {
      router.replace("/login");
      return;
    }

    // Check consent status before redirecting to training
    api
      .get("/consent/status")
      .then((data) => {
        if (data.all_accepted) {
          router.replace("/training");
        } else {
          router.replace("/consent");
        }
      })
      .catch(() => {
        // If consent endpoint fails (e.g. not implemented yet), go to training
        setStatus("Перенаправление...");
        router.replace("/training");
      });
  }, [router]);

  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="text-lg text-gray-500">{status}</div>
    </div>
  );
}
