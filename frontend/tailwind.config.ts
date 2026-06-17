import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
      colors: {
        ink: {
          950: "#05070d",
          900: "#0a0e1a",
          850: "#0f1422",
          800: "#141a2b",
          card: "#11172a",
        },
        neon: {
          cyan: "#00f0ff",
          magenta: "#ff2bd6",
          lime: "#00ff9c",
          amber: "#ffb020",
        },
        edge: { DEFAULT: "#1f2a44", strong: "#2c3a5e" },
      },
      boxShadow: {
        glow: "0 0 18px rgba(0,240,255,0.25)",
      },
    },
  },
  plugins: [],
};

export default config;