import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// The FastAPI backend runs on :8000 (uvicorn kopi_keys.main:app). Proxying /api avoids
// needing CORS changes in the backend during development.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
    // Lets the Sources page read data/policy_snapshots (ACTIVE + manifest) and data/schema.
    fs: { allow: [".."] },
  },
});
