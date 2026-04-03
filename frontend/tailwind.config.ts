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
          bg: "#ffffff",
          surface: "#f7f7f8",
          user: "#f4f4f4",
          accent: "#8B1A4A",
          input: "#f4f4f5",
          border: "#e5e5e5",
          text: "#111827",
          muted: "#6b7280",
        },
      },
    },
  },
  plugins: [],
};

export default config;
