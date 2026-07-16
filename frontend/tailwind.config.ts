import type { Config } from "tailwindcss";

/**
 * Los tokens del tema viven en variables CSS (--color-*) con valores hex
 * opacos. Tailwind v3 no puede inyectar opacidad en `var(...)` a secas, así
 * que los modificadores como `bg-primary/10` no generaban NINGUNA regla CSS
 * (clases muertas: resaltados de selección invisibles en toda la app).
 * La sintaxis de color relativo `rgb(from <color> r g b / alpha)` permite
 * derivar la opacidad de la variable en runtime manteniendo una única fuente
 * de verdad en globals.css / ThemeProvider.
 */
const withAlpha = (variable: string) =>
  `rgb(from var(${variable}) r g b / <alpha-value>)`;

const config: Config = {
  darkMode: 'class',
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./hooks/**/*.{js,ts,jsx,tsx}",
    "./lib/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: withAlpha("--color-bg"),
        foreground: withAlpha("--color-fg"),
        surface: withAlpha("--color-surface"),
        "surface-hover": withAlpha("--color-surface-hover"),
        "surface-inset": withAlpha("--color-surface-inset"),
        border: withAlpha("--color-border"),
        "border-subtle": withAlpha("--color-border-subtle"),
        muted: withAlpha("--color-muted"),
        "muted-fg": withAlpha("--color-muted-fg"),
        primary: {
          DEFAULT: withAlpha("--color-primary"),
          hover: withAlpha("--color-primary-hover"),
        },
        success: "#10B981",
        danger: "#EF4444",
      },
      fontFamily: {
        sans: ["var(--font-inter)", "system-ui", "sans-serif"],
        serif: ["var(--font-instrument-serif)", "Georgia", "serif"],
        mono: ["var(--font-mono)", "JetBrains Mono", "monospace"],
      },
      animation: {
        'fade-up': 'fadeUp 0.6s ease-out forwards',
        'fade-in': 'fadeIn 0.4s ease-out forwards',
        'pulse-glow': 'pulseGlow 2s ease-in-out infinite',
        'slide-in': 'slideIn 0.5s ease-out forwards',
        'slide-down': 'slideDown 0.35s cubic-bezier(0.16, 1, 0.3, 1) forwards',
      },
      keyframes: {
        fadeUp: {
          '0%': { opacity: '0', transform: 'translateY(20px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        pulseGlow: {
          '0%, 100%': { boxShadow: '0 0 20px rgba(0, 217, 255, 0.3)' },
          '50%': { boxShadow: '0 0 40px rgba(0, 217, 255, 0.6)' },
        },
        slideIn: {
          '0%': { opacity: '0', transform: 'translateX(-10px)' },
          '100%': { opacity: '1', transform: 'translateX(0)' },
        },
        slideDown: {
          '0%': { opacity: '0', transform: 'translateY(-100%)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
    },
  },
  plugins: [],
};
export default config;

