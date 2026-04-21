import type { Config } from "tailwindcss";
import tailwindcssAnimate from "tailwindcss-animate";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  darkMode: "class",
  theme: {
    extend: {
      /* ── Design Tokens ─────────────────────────────────── */
      borderRadius: {
        sm: "8px",
        md: "12px",
        lg: "16px",
        xl: "20px",
      },
      colors: {
        /* ── Brand ── */
        brand: {
          deep: "#311573",
          DEFAULT: "#6B4DC7",
          light: "#7E5FD9",
          muted: "rgba(107, 77, 199, 0.14)",
        },
        /* ── Violet scale (kept for legacy compat) ── */
        violet: {
          50: "#f5f3ff",
          100: "#ede9fe",
          200: "#ddd6fe",
          300: "#c4b5fd",
          400: "#a78bfa",
          500: "#8B5CF6",
          600: "#7C3AED",
          700: "#6D28D9",
          800: "#5B21B6",
          900: "#4C1D95",
        },
        surface: {
          50: "#fafafa",
          100: "#f4f4f5",
          200: "#e4e4e7",
          300: "#d4d4d8",
          400: "#a1a1aa",
          500: "#71717a",
          600: "#52525b",
          700: "#3f3f46",
          800: "#27272a",
          850: "#1e1e22",
          900: "#18181b",
          950: "#0d0d0f",
        },
        success: "#22c55e",
        warning: "#f59e0b",
        danger: "#ef4444",
        /* ── Gamified Cyber palette shortcuts ── */
        "vh-black": "#100F1A",
        "vh-purple": "#6B4DC7",
        "vh-darkPurple": "#311573",
        "vh-magenta": "#E028CC",
        "vh-red": "#E5484D",
        "vh-green": "#3DDC84",
        "vh-panel": "rgba(24, 23, 42, 0.65)",
        /* ── Gamification ── */
        "gf-xp": "var(--gf-xp)",
        "gf-streak": "var(--gf-streak)",
        "gf-levelup": "var(--gf-levelup)",
        "gf-reward": "var(--gf-reward)",
      },
      fontSize: {
        xs: ["0.875rem", { lineHeight: "1.25rem" }], // 14px min (was 12px)
      },
      fontFamily: {
        sans: ["var(--font-geist-sans)", "system-ui", "sans-serif"],
        display: ["var(--font-geist-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-geist-mono)", "monospace"],
        pixel: ["var(--font-vt323)", "monospace"],
      },
      /* ── Spacing scale (8px grid) ── */
      spacing: {
        "4.5": "18px",
        "13": "52px",
        "15": "60px",
        "18": "72px",
        "22": "88px",
      },
      animation: {
        "fade-in": "fade-in 0.4s ease-out",
        "fade-up": "fade-up 0.5s ease-out",
        "slide-in-right": "slide-in-right 0.3s ease-out",
        "scale-in": "scale-in 0.2s ease-out",
        float: "float 6s ease-in-out infinite",
        "spin-slow": "spin 60s linear infinite",
        "spin-slow-reverse": "spin 40s linear infinite reverse",
        shimmer: "shimmer 2s linear infinite",
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
      },
      keyframes: {
        "fade-in": {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(12px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "slide-in-right": {
          "0%": { opacity: "0", transform: "translateX(16px)" },
          "100%": { opacity: "1", transform: "translateX(0)" },
        },
        "scale-in": {
          "0%": { opacity: "0", transform: "scale(0.95)" },
          "100%": { opacity: "1", transform: "scale(1)" },
        },
        float: {
          "0%, 100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-10px)" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
        "accordion-down": {
          from: { height: "0" },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: "0" },
        },
      },
      backdropBlur: {
        xs: "2px",
      },
      boxShadow: {},
    },
  },
  plugins: [tailwindcssAnimate],
};

export default config;
