import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Send /api calls to the Flask backend (py -m backend.app), so the browser sees one origin.
    proxy: {
      "/api": "http://127.0.0.1:5000",
    },
  },
});
