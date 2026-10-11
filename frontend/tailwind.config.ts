import type { Config } from "tailwindcss";

const token = (name: string) => `rgb(var(--${name}) / <alpha-value>)`;
const scale = (name: string, steps: number[]) => Object.fromEntries(steps.map((step) => [step, token(`${name}-${step}`)]));

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        slate: scale("slate", [50, 100, 200, 300, 400, 500, 600, 700, 800, 900]),
        brand: scale("brand", [50, 100, 500, 600, 700]),
        surface: token("surface"),
        ink: token("ink"),
        code: token("code"),
        "code-fg": token("code-fg"),
      },
      fontFamily: {
        sans: ["var(--font-geist)", "Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["var(--font-geist-mono)", "ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
      },
      borderRadius: {
        md: "4px",
        lg: "4px",
        xl: "8px",
        "2xl": "12px",
      },
      boxShadow: {
        card: "0 1px 2px 0 rgb(var(--shadow) / 0.05)",
        float: "0 1px 2px 0 rgb(var(--shadow) / 0.05), 0 8px 24px -8px rgb(var(--shadow) / 0.12)",
      },
    },
  },
  plugins: [],
};

export default config;
