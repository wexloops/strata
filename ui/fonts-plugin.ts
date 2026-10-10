import type { Plugin } from "vite";
// Fontsource CSS lists woff2 + woff; every browser we target reads woff2, so drop the woff fallback
// (halves font weight, matters for the single-file report).
export function woff2Only(): Plugin {
  return {
    name: "strata-woff2-only",
    enforce: "pre",
    transform(code, id) {
      if (!id.includes("@fontsource") || !id.split("?")[0].endsWith(".css")) return null;
      return { code: code.replace(/,\s*url\([^)]*\.woff\)\s*format\(["']woff["']\)/g, ""), map: null };
    },
  };
}
