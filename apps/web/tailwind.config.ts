import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        "calm-dark": "#0F172A",
        "calm-card": "#111827",
        "calm-primary": "#6366F1",
        "calm-secondary": "#22C55E",
        "calm-text": "#E5E7EB",
        "calm-muted": "#9CA3AF",
        "calm-border": "rgba(255,255,255,0.06)",
      },
      boxShadow: {
        "calm-sm": "0 2px 8px rgba(0, 0, 0, 0.2)",
        "calm-md": "0 8px 24px rgba(0, 0, 0, 0.25)",
        "calm-lg": "0 16px 40px rgba(0, 0, 0, 0.3)",
      },
      animation: {
        "fade-in": "fadeIn 0.25s ease-out",
        "slide-up": "slideUp 0.3s cubic-bezier(0.16, 1, 0.3, 1)",
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        slideUp: {
          "0%": { transform: "translateY(16px)", opacity: "0" },
          "100%": { transform: "translateY(0)", opacity: "1" },
        },
      },
    },
  },
  plugins: [],
};

export default config;
