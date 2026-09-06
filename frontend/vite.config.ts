import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // The browser walk-through under e2e/ is Playwright's, not Vitest's: it
  // needs a running backend and a real Chrome. Run it with
  // `python scripts/e2e_browser.py`.
  test: { exclude: ["e2e/**", "e2e-production/**", "node_modules/**", "dist/**"] },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.CAS_API_URL || "http://127.0.0.1:8001",
        changeOrigin: true,
      },
    },
  },
});
