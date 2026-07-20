import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const crossoriginPlugin = () => ({
  name: 'crossorigin-use-credentials',
  transformIndexHtml(html: string) {
    return html.replace(/crossorigin/g, (match, offset) => {
      const tagStart = html.lastIndexOf('<', offset);
      const tagEnd = html.indexOf('>', offset);
      if (tagStart !== -1 && tagEnd !== -1) {
        const tagContent = html.substring(tagStart, tagEnd);
        if (tagContent.includes('porsche.com') || tagContent.includes('fonts.gstatic.com')) {
          return 'crossorigin="anonymous"';
        }
      }
      return 'crossorigin="use-credentials"';
    });
  }
});


// Served by FastAPI under /ms/bidding/ in the ecosystem; base is relative so the
// built assets resolve behind the nginx path prefix.
export default defineConfig({
  plugins: [react(), crossoriginPlugin()],
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
