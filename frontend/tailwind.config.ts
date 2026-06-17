import type { Config } from "tailwindcss";

/** Mirror proj-theseus/tailwind.config.js — keep in sync with Theseus tokens */
const config: Config = {
  darkMode: "class",
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
          700: "#1c2338",
          600: "#283151",
          card: "#11172a",
        },
        neon: {
          cyan: "#00f0ff",
          magenta: "#ff2bd6",
          lime: "#00ff9c",
          amber: "#ffb020",
          red: "#ff3b6b",
        },
        edge: { DEFAULT: "#1f2a44", strong: "#2c3a5e" },
      },
      boxShadow: {
        glow: "0 0 18px rgba(0,240,255,0.25), 0 0 2px rgba(0,240,255,0.5) inset",
        magenta:
          "0 0 18px rgba(255,43,214,0.2), 0 0 2px rgba(255,43,214,0.45) inset",
      },
    },
  },
  plugins: [],
};

export default config;