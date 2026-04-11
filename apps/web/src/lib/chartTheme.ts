/**
 * Shared Chart.js theme configuration for dark/light mode.
 *
 * IMPORTANT: Chart.js renders on <canvas> and CANNOT resolve CSS var().
 * Always use cssVar() or getChartTheme() colors — never raw "var(--...)".
 *
 * Usage:
 *   import { getChartTheme, cssVar } from "@/lib/chartTheme";
 *   const theme = getChartTheme();
 *   <Bar options={{ ...options, ...theme.defaults }} />
 */

/** Resolve a CSS custom property to its computed value (canvas-safe). */
export function cssVar(name: string, fallback: string): string {
  if (typeof window === "undefined") return fallback;
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}

export function getChartTheme() {
  const gridColor = cssVar("--chart-grid", "rgba(255,255,255,0.18)");
  const textColor = cssVar("--chart-text", "#E0DCF0");
  const lineColor = cssVar("--chart-line", "#A894FF");
  const fillColor = cssVar("--chart-fill", "rgba(168,148,255,0.28)");
  const tooltipBg = cssVar("--chart-tooltip-bg", "#252438");
  const tooltipBorder = cssVar("--chart-tooltip-border", "rgba(255,255,255,0.22)");
  const bar1 = cssVar("--chart-bar-1", "#A894FF");
  const bar2 = cssVar("--chart-bar-2", "#4AE89A");
  const bar3 = cssVar("--chart-bar-3", "#FFD060");
  const bar4 = cssVar("--chart-bar-4", "#FF7EB3");

  // Semantic colors resolved for canvas
  const accent = cssVar("--accent", "#7C6AE8");
  const accentMuted = cssVar("--accent-muted", "rgba(124,106,232,0.14)");
  const danger = cssVar("--danger", "#E5484D");
  const warning = cssVar("--warning", "#E8A630");
  const success = cssVar("--success", "#3DDC84");
  const magenta = cssVar("--magenta", "#D926B8");
  const info = cssVar("--info", "#5B9EE9");

  return {
    colors: {
      line: lineColor, fill: fillColor,
      bar1, bar2, bar3, bar4,
      accent, accentMuted, danger, warning, success, magenta, info,
      text: textColor, grid: gridColor,
    },
    defaults: {
      plugins: {
        legend: {
          labels: {
            color: textColor,
            font: { size: 14, family: "var(--font-geist-sans), system-ui, sans-serif" },
            padding: 18,
            boxWidth: 14,
            boxHeight: 14,
            useBorderRadius: true,
            borderRadius: 3,
          },
        },
        tooltip: {
          backgroundColor: tooltipBg,
          titleColor: "#fff",
          bodyColor: textColor,
          borderColor: tooltipBorder,
          borderWidth: 1,
          padding: 14,
          cornerRadius: 10,
          titleFont: { size: 14, weight: "bold" as const },
          bodyFont: { size: 14 },
          boxPadding: 6,
        },
      },
      scales: {
        x: {
          grid: { color: gridColor },
          ticks: { color: textColor, font: { size: 14 } },
          border: { color: "transparent" },
        },
        y: {
          grid: { color: gridColor },
          ticks: { color: textColor, font: { size: 14 } },
          border: { color: "transparent" },
        },
      },
    },
  };
}
