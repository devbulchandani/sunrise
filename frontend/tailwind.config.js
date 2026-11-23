/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        base: "#05080D",
        "base-soft": "#070C13",
        surface: "#0A111A",
        "surface-2": "#0F1824",
        "surface-3": "#152131",
        edge: "#1A2433",
        "edge-bright": "#2A3A50",
        ink: "#F2F5F9",
        "ink-dim": "#A6B2C2",
        "ink-faint": "#7B8899",
        amber: {
          DEFAULT: "#F5A623",
          dim: "#8A4E0A",
          soft: "#2A1C08",
        },
        bull: "#42D9A0",
        bear: "#FF6B81",
        heal: "#5EEAD4",
        info: "#7DD3FC",
      },
      fontFamily: {
        sans: ["Geist", "Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        display: ["Instrument Serif", "Georgia", "ui-serif", "serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      boxShadow: {
        panel:
          "inset 0 1px 0 0 rgba(255,255,255,0.035), 0 30px 70px -50px rgba(0,0,0,0.95)",
        "panel-hover":
          "inset 0 1px 0 0 rgba(255,255,255,0.06), 0 36px 80px -45px rgba(0,0,0,0.95)",
        "glow-amber":
          "0 0 0 1px rgba(245,166,35,0.16), 0 24px 70px -35px rgba(245,166,35,0.28)",
        "glow-bear":
          "0 0 0 1px rgba(255,107,129,0.16), 0 24px 70px -35px rgba(255,107,129,0.24)",
      },
      backgroundImage: {
        dawn:
          "radial-gradient(110% 80% at 12% -10%, rgba(245,166,35,0.13), transparent 55%), radial-gradient(80% 60% at 92% -4%, rgba(94,234,212,0.07), transparent 60%)",
        grid:
          "linear-gradient(rgba(255,255,255,0.028) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.028) 1px, transparent 1px)",
      },
      keyframes: {
        rise: {
          from: { opacity: "0", transform: "translateY(16px)", filter: "blur(6px)" },
          to: { opacity: "1", transform: "translateY(0)", filter: "blur(0)" },
        },
        fade: {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
        marquee: {
          from: { transform: "translateX(0)" },
          to: { transform: "translateX(-50%)" },
        },
        pulseSoft: {
          "0%, 100%": { opacity: "1", transform: "scale(1)" },
          "50%": { opacity: "0.45", transform: "scale(0.86)" },
        },
        sweep: {
          from: { backgroundPosition: "200% 0" },
          to: { backgroundPosition: "-200% 0" },
        },
        glow: {
          "0%, 100%": { opacity: "0.55" },
          "50%": { opacity: "1" },
        },
        draw: {
          from: { strokeDashoffset: "300" },
          to: { strokeDashoffset: "0" },
        },
      },
      animation: {
        rise: "rise 0.7s cubic-bezier(0.16, 1, 0.3, 1) both",
        fade: "fade 0.5s ease-out both",
        marquee: "marquee 55s linear infinite",
        "pulse-soft": "pulseSoft 2.4s ease-in-out infinite",
        sweep: "sweep 8s linear infinite",
        glow: "glow 3.2s ease-in-out infinite",
        draw: "draw 1.4s ease-out both",
      },
      transitionTimingFunction: {
        "out-expo": "cubic-bezier(0.16, 1, 0.3, 1)",
      },
    },
  },
  plugins: [],
};
