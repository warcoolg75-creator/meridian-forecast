import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The API (`make run`) listens on 127.0.0.1:8000. Proxying keeps the browser on a single
// origin: the backend needs no CORS configuration, and the SameSite refresh cookie is
// first-party. /docs and /openapi.json are the API reference linked from the footer.
const API = "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: { "/api": API, "/docs": API, "/openapi.json": API },
  },
  preview: {
    host: "127.0.0.1",
    port: 4173,
    strictPort: true,
  },
});
