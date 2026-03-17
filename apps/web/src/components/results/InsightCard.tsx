"use client";

import { TrendingDown, TrendingUp } from "lucide-react";

interface InsightCardProps {
  type: "drop" | "recovery";
  title: string;
  description: string;
  timestamp?: string;
}

export default function InsightCard({
  type,
  title,
  description,
  timestamp,
}: InsightCardProps) {
  const isDrop = type === "drop";

  return (
    <div
      className={`rounded-lg border p-4 ${
        isDrop
          ? "border-vh-red/20 bg-vh-red/5"
          : "border-vh-green/20 bg-vh-green/5"
      }`}
    >
      <div className="flex items-start gap-3">
        <div
          className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${
            isDrop ? "bg-vh-red/10" : "bg-vh-green/10"
          }`}
        >
          {isDrop ? (
            <TrendingDown className="h-4 w-4 text-vh-red" />
          ) : (
            <TrendingUp className="h-4 w-4 text-vh-green" />
          )}
        </div>
        <div>
          <div className="flex items-center gap-2">
            <h4
              className={`font-mono text-xs font-bold uppercase tracking-wider ${
                isDrop ? "text-vh-red" : "text-vh-green"
              }`}
            >
              {isDrop ? "Critical Drop" : "Key Recovery"}
            </h4>
            {timestamp && (
              <span className="font-mono text-[10px] text-white/20">
                {timestamp}
              </span>
            )}
          </div>
          <p className="mt-1 text-sm font-medium text-white/80">{title}</p>
          <p className="mt-0.5 text-xs text-white/40">{description}</p>
        </div>
      </div>
    </div>
  );
}
