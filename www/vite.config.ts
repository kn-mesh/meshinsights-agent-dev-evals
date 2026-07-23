import { resolve } from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: [
      { find: "@eval-ui", replacement: resolve(__dirname, "../agent-dev-eval-ui/web/src") },
      { find: "@use-case", replacement: resolve(__dirname, "src/use_case") },
      { find: "@tanstack/react-query", replacement: resolve(__dirname, "node_modules/@tanstack/react-query") },
      { find: "plotly.js-cartesian-dist-min", replacement: resolve(__dirname, "node_modules/plotly.js-cartesian-dist-min") },
      { find: "react-plotly.js/factory", replacement: resolve(__dirname, "node_modules/react-plotly.js/dist/factory.mjs") },
    ],
    dedupe: ["react", "react-dom"],
  },
  server: {
    proxy: { "/api": "http://127.0.0.1:8765" },
  },
});
