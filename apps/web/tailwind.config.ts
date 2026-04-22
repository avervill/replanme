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
        ink: "#11212d",
        mist: "#d6e5e3",
        surf: "#8aa6a3",
        ember: "#ff7a59",
        glow: "#f4c95d",
      },
      boxShadow: {
        soft: "0 24px 60px rgba(17, 33, 45, 0.14)",
      },
    },
  },
  plugins: [],
};

export default config;

