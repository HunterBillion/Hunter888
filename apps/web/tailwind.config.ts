import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
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
        /* ── Design concept colors ── */
        "vh-black": "#050505",
        "vh-purple": "#8B5CF6",
        "vh-darkPurple": "#6D28D9",
        "vh-magenta": "#E028CC",
        "vh-red": "#FF3333",
        "vh-green": "#00FF66",
        "vh-panel": "rgba(15, 15, 20, 0.6)",
      },
      fontFamily: {
        sans: ["Plus Jakarta Sans", "system-ui", "sans-serif"],
        display: ["Plus Jakarta Sans", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
      animation: {
        scanline: "scanline 8s linear infinite",
        "pulse-glow": "pulse-glow 2s ease-in-out infinite",
        "fade-in": "fade-in 0.4s ease-out",
        "fade-up": "fade-up 0.5s ease-out",
        "slide-in-right": "slide-in-right 0.3s ease-out",
        "scale-in": "scale-in 0.2s ease-out",
        float: "float 6s ease-in-out infinite",
        "spin-slow": "spin 60s linear infinite",
        "spin-slow-reverse": "spin 40s linear infinite reverse",
        "bounce-dots": "bounce-dots 1.4s ease-in-out infinite",
        "glow-pulse": "glow-pulse 2s ease-in-out infinite alternate",
        shimmer: "shimmer 2s linear infinite",
      },
      keyframes: {
        scanline: {
          "0%": { transform: "translateY(-100vh)" },
          "100%": { transform: "translateY(100vh)" },
        },
        "pulse-glow": {
          "0%, 100%": { opacity: "0.4" },
          "50%": { opacity: "1" },
        },
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
        "bounce-dots": {
          "0%, 100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-6px)" },
        },
        "glow-pulse": {
          "0%": { opacity: "0.2", transform: "scale(1)" },
          "100%": { opacity: "0.6", transform: "scale(1.05)" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
      },
      backdropBlur: {
        xs: "2px",
      },
      boxShadow: {
        glow: "0 0 20px rgba(139, 92, 246, 0.3)",
        "glow-lg": "0 0 40px rgba(139, 92, 246, 0.4)",
        "glow-sm": "0 0 10px rgba(139, 92, 246, 0.2)",
        "glow-magenta": "0 0 30px rgba(224, 40, 204, 0.4)",
        "glow-green": "0 0 20px rgba(0, 255, 102, 0.3)",
        "glow-red": "0 0 20px rgba(255, 51, 51, 0.3)",
      },
    },
  },
  plugins: [],
};

export default config;
