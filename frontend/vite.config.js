import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development the API runs on :8000; the proxy avoids CORS and mirrors the nginx setup in Docker.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": "http://localhost:8000" },
  },
  build: {
    rollupOptions: { output: { manualChunks: { charts: ["recharts"], vendor: ["react", "react-dom", "react-router-dom"] } } },
  },
  test: { environment: "node" },
});
