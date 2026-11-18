import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// In development, the React app runs on :5173 and the FastAPI backend on :8000.
// The proxy forwards every /api/* request to the backend, so the frontend can
// call "/api/parks" without worrying about ports or CORS while you develop.
// In production (Vercel) set VITE_API_BASE_URL to the Render backend URL instead.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  // Charts and React in their own files: smaller downloads, and they stay cached between deploys.
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          react: ["react", "react-dom", "react-router-dom"],
          charts: ["recharts"],
        },
      },
    },
  },
  // `npm test` runs Vitest in a simulated browser (jsdom).
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.js",
  },
});
