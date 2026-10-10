// Second build: one self-contained HTML (JS, CSS and fonts inlined) used by exporters/report.py.
import { defineConfig } from "vite";
import { viteSingleFile } from "vite-plugin-singlefile";
import { resolve } from "node:path";
import { woff2Only } from "./fonts-plugin";

export default defineConfig({
  root: import.meta.dirname,
  publicDir: false,
  plugins: [woff2Only(), viteSingleFile({ removeViteModuleLoader: true })],
  build: {
    outDir: resolve(import.meta.dirname, "../strata/web"),
    emptyOutDir: false,
    target: "es2022",
    assetsInlineLimit: 100_000_000,
    cssCodeSplit: false,
    rollupOptions: { input: resolve(import.meta.dirname, "report_template.html") },
  },
});
