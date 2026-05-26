import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        safar: {
          red: "#c0392b",
          navy: "#1a2744",
          cream: "#f7f5f2",
        },
      },
    },
  },
  plugins: [],
};

export default config;
