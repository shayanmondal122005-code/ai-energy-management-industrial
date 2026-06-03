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
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        card: "hsl(var(--card))",
        "card-foreground": "hsl(var(--card-foreground))",
        input: "hsl(var(--input))",
        primary: "hsl(var(--primary))",
        "primary-foreground": "hsl(var(--primary-foreground))",
        destructive: "hsl(var(--destructive))",
        bg:      "#060a12",
        panel:   "#0b1120",
        border:  "hsl(var(--border))",
        muted:   "hsl(var(--muted))",
        "muted-foreground": "hsl(var(--muted-foreground))",
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
