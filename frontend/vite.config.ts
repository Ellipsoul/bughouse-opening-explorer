import { defineConfig } from "vite";

export default defineConfig({
  // Proxy API calls to the local FastAPI query server so the page stays same-origin (no CORS).
  server: {
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
  build: { target: "es2020" },
});
