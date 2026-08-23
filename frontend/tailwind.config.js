/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        base: "#0a0e14",
        surface: "#11161f",
        "surface-2": "#161d29",
        edge: "#1c2530",
        "edge-bright": "#2a3646",
        ink: "#d5dbe4",
        "ink-dim": "#8b95a5",
        "ink-faint": "#5a6472",
        amber: {
          DEFAULT: "#f59e0b",
          dim: "#78350f",
          soft: "rgba(245,158,11,0.12)",
        },
        bull: "#10b981",
        bear: "#ef4444",
        heal: "#a855f7",
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      animation: {
        "live-dot": "liveDot 1.6s ease-in-out infinite",
        "heal-dot": "healDot 1.2s ease-in-out infinite",
        "fade-in": "fadeIn 0.35s ease-out both",
        "fade-in-up": "fadeInUp 0.4s ease-out both",
        "glow-critical": "glowCritical 2.2s ease-in-out infinite",
        shimmer: "shimmer 1.8s linear infinite",
      },
      keyframes: {
        liveDot: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.25" },
        },
        healDot: {
          "0%, 100%": { opacity: "1", transform: "scale(1)" },
          "50%": { opacity: "0.45", transform: "scale(1.35)" },
        },
        fadeIn: {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
        fadeInUp: {
          from: { opacity: "0", transform: "translateY(10px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        glowCritical: {
          "0%, 100%": {
            boxShadow:
              "0 0 0 1px rgba(239,68,68,0.55), 0 0 24px rgba(239,68,68,0.18)",
          },
          "50%": {
            boxShadow:
              "0 0 0 1px rgba(239,68,68,0.9), 0 0 42px rgba(239,68,68,0.32)",
          },
        },
        shimmer: {
          from: { backgroundPosition: "200% 0" },
          to: { backgroundPosition: "-200% 0" },
        },
      },
    },
  },
  plugins: [],
};
