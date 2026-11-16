/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: ["class", '[data-theme="dark"]'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Instrument Sans Variable"', "ui-sans-serif", "system-ui", "sans-serif"],
      },
      colors: {
        paper: "rgb(var(--paper) / <alpha-value>)",
        surface: "rgb(var(--surface) / <alpha-value>)",
        sunken: "rgb(var(--sunken) / <alpha-value>)",
        line: "rgb(var(--line) / <alpha-value>)",
        ink: "rgb(var(--ink) / <alpha-value>)",
        muted: "rgb(var(--muted) / <alpha-value>)",
        you: "rgb(var(--you) / <alpha-value>)",
        partner: "rgb(var(--partner) / <alpha-value>)",
        good: "rgb(var(--good) / <alpha-value>)",
        bad: "rgb(var(--bad) / <alpha-value>)",
        warn: "rgb(var(--warn) / <alpha-value>)",
      },
      borderRadius: { lg: "10px", xl: "14px" },
      boxShadow: {
        lift: "0 1px 2px rgb(23 32 51 / 0.06), 0 4px 16px -6px rgb(23 32 51 / 0.12)",
        pop: "0 12px 40px -12px rgb(23 32 51 / 0.35)",
      },
    },
  },
  plugins: [],
};
