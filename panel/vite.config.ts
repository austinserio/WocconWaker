import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  base: "/panel/",
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: `http://127.0.0.1:${process.env.WOCCON_BACKEND_PORT || process.env.PORT || "8000"}`,
        changeOrigin: true,
      },
    },
  },
});
