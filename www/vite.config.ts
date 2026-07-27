import { resolve } from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: [
      { find: "@eval-ui", replacement: resolve(__dirname, "../agent-dev-eval-ui/web/src") },
      { find: "@use-case", replacement: resolve(__dirname, "src/use_case") },
      { find: "react/jsx-dev-runtime", replacement: resolve(__dirname, "node_modules/react/jsx-dev-runtime") },
      { find: "react/jsx-runtime", replacement: resolve(__dirname, "node_modules/react/jsx-runtime") },
      { find: "react-dom", replacement: resolve(__dirname, "node_modules/react-dom") },
      { find: "react", replacement: resolve(__dirname, "node_modules/react") },
      { find: "lucide-react", replacement: resolve(__dirname, "node_modules/lucide-react") },
      { find: "@radix-ui/react-select", replacement: resolve(__dirname, "node_modules/@radix-ui/react-select") },
      { find: "@tanstack/react-query", replacement: resolve(__dirname, "node_modules/@tanstack/react-query") },
      { find: "plotly.js-cartesian-dist-min", replacement: resolve(__dirname, "node_modules/plotly.js-cartesian-dist-min") },
      { find: "react-plotly.js/factory", replacement: resolve(__dirname, "node_modules/react-plotly.js/dist/factory.mjs") },
    ],
    dedupe: ["react", "react-dom"],
    conditions: ["browser", "module", "import", "default"],
  },
  server: {
    proxy: { "/api": "http://127.0.0.1:8765" },
  },
});
