import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        "vh-black": "#050505",
        "vh-purple": "#8A2BE2",
        "vh-darkPurple": "#4B0082",
        "vh-magenta": "#E028CC",
        "vh-red": "#FF3333",
        "vh-green": "#00FF66",
        "vh-panel": "rgba(15, 15, 20, 0.6)",
        primary: {
          50: "#eff6ff",
          100: "#dbeafe",
          500: "#3b82f6",
          600: "#2563eb",
          700: "#1d4ed8",
        },
        success: "#22c55e",
        warning: "#f59e0b",
        danger: "#ef4444",
      },
      fontFamily: {
        sans: ["Space Grotesk", "system-ui", "sans-serif"],
        display: ["Rajdhani", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
      animation: {
        scanline: "scanline 8s linear infinite",
        "pulse-glow": "pulse-glow 2s ease-in-out infinite",
        "fade-in": "fade-in 0.3s ease-out",
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
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
    },
  },
  plugins: [],
};

export default config;
