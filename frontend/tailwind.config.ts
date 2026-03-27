import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx}",
    "./components/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        wine: {
          bg: "#0D0D0D",
          surface: "#1A1A2E",
          user: "#4A1942",
          accent: "#8B1A4A",
          input: "#1A1A1A",
          border: "#333333",
          text: "#E0E0E0",
          muted: "#888888",
        },
      },
    },
  },
  plugins: [],
};

export default config;
