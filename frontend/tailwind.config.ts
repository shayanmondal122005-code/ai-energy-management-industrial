import type { Config } from "tailwindcss"

const config: Config = {
  darkMode: "class",
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        bg:      "#060a12",
        panel:   "#0b1120",
        border:  "#1c2d47",
        muted:   "#3d5a80",
        accent:  "#2563eb",
        solar:   "#f59e0b",
        battery: "#10b981",
        load:    "#ef4444",
        grid:    "#8b5cf6",
      },
      fontFamily: {
        mono: ["JetBrains Mono", "monospace"],
      },
    },
  },
  plugins: [],
}
export default config
