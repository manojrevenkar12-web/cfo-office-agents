/// <reference types="vitest" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  base: "./",
  server: { proxy: { "/api": "http://localhost:8080" } },
  test: { globals: true, environment: "jsdom", setupFiles: ["./src/test/setup.ts"], css: false },
});
