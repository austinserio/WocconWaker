/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "sans-serif",
        ],
      },
      colors: {
        render: {
          canvas: "#0a0a0a",
          surface: "#111111",
          elevated: "#1a1a1a",
          border: "#2a2a2a",
          "border-hover": "#3d3d3d",
          muted: "#888888",
          subtle: "#666666",
          text: "#f5f5f5",
          accent: "#5e6ad2",
        },
      },
      boxShadow: {
        card: "0 1px 2px rgba(0,0,0,0.4), 0 4px 12px rgba(0,0,0,0.25)",
        "card-hover": "0 4px 16px rgba(0,0,0,0.45), 0 0 0 1px rgba(255,255,255,0.06)",
        glow: "0 0 20px rgba(255,255,255,0.08)",
      },
      animation: {
        "fade-in": "fadeIn 0.35s ease-out",
        "slide-up": "slideUp 0.4s ease-out",
        "pulse-soft": "pulseSoft 2s ease-in-out infinite",
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        slideUp: {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        pulseSoft: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.7" },
        },
      },
      transitionDuration: {
        DEFAULT: "200ms",
      },
    },
  },
  plugins: [],
};
