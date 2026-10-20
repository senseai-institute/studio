// Copyright 2026 SenseAI Institute
// SPDX-License-Identifier: Apache-2.0
import { defineConfig } from "vite";

export default defineConfig({
  base: "/studio/",
  build: {
    outDir: "../src/senseai_studio/static",
    emptyOutDir: true,
    sourcemap: false,
  },
  server: {
    proxy: { "/api": "http://127.0.0.1:8200" },
  },
});
