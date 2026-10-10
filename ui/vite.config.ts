import { defineConfig, type Plugin } from "vite";
import { createReadStream, statSync, existsSync } from "node:fs";
import { resolve, join, normalize, extname } from "node:path";
import { woff2Only } from "./fonts-plugin";

// Set STRATA_API=http://127.0.0.1:8765 to develop against a running `strata serve`.
const api = process.env.STRATA_API;

// `vite preview` serves only the build output; this keeps /demo/* (gitignored fixture + audio) reachable there,
// with Range support so <audio> can seek. Never copied into the build.
function demoFiles(): Plugin {
  const dir = resolve(import.meta.dirname, "public/demo");
  const types: Record<string, string> = { ".json": "application/json", ".wav": "audio/wav", ".mp3": "audio/mpeg", ".flac": "audio/flac" };
  // Without a backend, answer /api/* with 204 so the UI falls into demo mode without a 404 in the console.
  const noApi = (_req: unknown, res: { statusCode: number; end: () => void }) => { res.statusCode = 204; res.end(); };
  return {
    name: "strata-demo-files",
    configureServer(server) {
      if (!api) server.middlewares.use("/api", noApi);
    },
    configurePreviewServer(server) {
      if (!api) server.middlewares.use("/api", noApi);
      server.middlewares.use("/demo", (req, res, next) => {
        const rel = normalize(decodeURIComponent((req.url || "/").split("?")[0])).replace(/^([/\\])+/, "");
        const file = join(dir, rel);
        if (!file.startsWith(dir) || !existsSync(file)) return next();
        const size = statSync(file).size;
        res.setHeader("content-type", types[extname(file)] || "application/octet-stream");
        res.setHeader("accept-ranges", "bytes");
        const m = /bytes=(\d*)-(\d*)/.exec(req.headers.range || "");
        if (m) {
          const start = m[1] ? +m[1] : 0, end = m[2] ? Math.min(+m[2], size - 1) : size - 1;
          res.statusCode = 206;
          res.setHeader("content-range", `bytes ${start}-${end}/${size}`);
          res.setHeader("content-length", end - start + 1);
          createReadStream(file, { start, end }).pipe(res);
        } else {
          res.setHeader("content-length", size);
          createReadStream(file).pipe(res);
        }
      });
    },
  };
}


export default defineConfig(({ command }) => ({
  root: import.meta.dirname,
  publicDir: command === "serve" ? "public" : false,
  plugins: [demoFiles(), woff2Only()],
  build: {
    outDir: resolve(import.meta.dirname, "../strata/web"),
    emptyOutDir: true,
    target: "es2022",
    chunkSizeWarningLimit: 800,
  },
  server: {
    port: 5180,
    proxy: api ? { "/api": { target: api, ws: true, changeOrigin: true } } : undefined,
  },
  preview: { port: 4173, proxy: api ? { "/api": { target: api, ws: true, changeOrigin: true } } : undefined },
}));
