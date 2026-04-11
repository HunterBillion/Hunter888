"use client";

import { Info } from "lucide-react";
import { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider } from "@/components/ui/Tooltip";

interface InfoButtonProps {
  text: string;
  size?: number;
  side?: "top" | "bottom" | "left" | "right";
  className?: string;
}

/**
 * Standardized info (i) button with tooltip.
 * Always 18px icon, hover reveals tooltip after 200ms.
 *
 * Usage:
 *   <InfoButton text="Это показатель среднего балла" />
 */
export function InfoButton({ text, size = 18, side = "top", className = "" }: InfoButtonProps) {
  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            className={`inline-flex items-center justify-center rounded-full transition-colors hover:opacity-80 focus:outline-none ${className}`}
            style={{ width: size + 8, height: size + 8, color: "var(--text-muted)" }}
            aria-label="Информация"
          >
            <Info size={size} />
          </button>
        </TooltipTrigger>
        <TooltipContent side={side} className="max-w-[280px] text-sm leading-relaxed">
          {text}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
