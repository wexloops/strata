// Dev helper: orbs screenshots against a running STRATA server (proxied by `STRATA_API=... vite preview --port 4174`).
// node tests/orbs-shots.mjs [base] [trackTitle] t1 t2 ...
import { chromium } from "@playwright/test";
const [base = "http://127.0.0.1:4174", title = "strangeloop-parallel-processing", ...ts] = process.argv.slice(2);
const times = ts.length ? ts.map(Number) : [16, 58, 100];
const b = await chromium.launch({ args: ["--autoplay-policy=no-user-gesture-required", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
const p = await b.newPage({ viewport: { width: 1920, height: 1080 } });
p.on("console", (m) => m.type() === "error" && console.log("console:", m.text()));
p.on("pageerror", (e) => console.log("pageerror:", String(e)));
const tracks = await (await fetch(`${base}/api/tracks`)).json();
const tr = tracks.find((x) => x.title === title);
await p.goto(`${base}/?track=${tr.id}`);
await p.waitForSelector("body[data-ready='1']");
await p.keyboard.press("v");
for (const t of times) {
  await p.evaluate((t) => window.__strata.seek(t), t - 0.9);
  await p.keyboard.press("Space");
  await p.waitForTimeout(900);
  await p.screenshot({ path: `tests/screenshots/orbs-${t.toFixed(0)}s.png` });
  await p.keyboard.press("Space");
  console.log("shot", t, await p.evaluate(() => window.__strata.time()));
}
await b.close();
