import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Served by FastAPI under /ms/bidding/ in the ecosystem; base is relative so the
// built assets resolve behind the nginx path prefix.
export default defineConfig({
  plugins: [react()],
  base: "./",
  server: {
    port: 5174,
    // Dev proxy so `npm run dev` talks to a locally-running bidding backend.
    proxy: {
      "/api": { target: "http://localhost:8014", changeOrigin: true },
    },
  },
  build: { outDir: "dist" },
});
