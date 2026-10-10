// Dev helper: close-ups of the MIX orb (seam check) at several times and pixel ratios.
import { chromium } from "@playwright/test";
const base = process.argv[2] || "http://127.0.0.1:4174";
const b = await chromium.launch({ args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
const tracks = await (await fetch(`${base}/api/tracks`)).json();
const tr = tracks.find((x) => x.title === "strangeloop-parallel-processing");
for (const dpr of [1, 2]) {
  const p = await b.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: dpr });
  p.on("console", (m) => m.type() === "error" && console.log("console:", m.text()));
  await p.goto(`${base}/?track=${tr.id}`);
  await p.waitForSelector("body[data-ready='1']");
  await p.keyboard.press("v");
  for (const t of [16, 58, 100]) {
    await p.evaluate((t) => window.__strata.seek(t), t);
    await p.waitForTimeout(300);
    await p.screenshot({ path: `tests/screenshots/mix-${t}s-dpr${dpr}.png`, clip: { x: 780, y: 340, width: 360, height: 360 } });
  }
  await p.close();
}
await b.close();
