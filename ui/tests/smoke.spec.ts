// Smoke test in DEMO mode (no STRATA server): fixture analysis + audio from ui/public/demo.
import { test, expect, type Page, type ConsoleMessage } from "@playwright/test";
import { mkdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

const SHOTS = resolve(import.meta.dirname, "screenshots");
const DEMO_TITLE: string = JSON.parse(readFileSync(resolve(import.meta.dirname, "../public/demo/sample_analysis.json"), "utf8")).track.title;
mkdirSync(SHOTS, { recursive: true });

type S = { mode: string; time: () => number; playing: () => boolean; playheadX: () => number; webgl2: () => boolean };
const strata = (page: Page) => page.evaluate(() => {
  const s = (window as unknown as { __strata: S }).__strata;
  return { mode: s.mode, t: s.time(), x: s.playheadX(), playing: s.playing(), gl: s.webgl2() };
});

async function boot(page: Page, errors: string[]) {
  page.on("console", (m: ConsoleMessage) => { if (m.type() === "error") errors.push(m.text()); });
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.goto("/");
  await page.waitForSelector("body[data-ready='1']", { timeout: 20_000 });
}

test("lanes render, play moves the playhead, visualizer has WebGL2", async ({ page }) => {
  const errors: string[] = [];
  await boot(page, errors);
  expect((await strata(page)).mode).toBe("demo");

  await expect(page.locator(".trk-x")).toHaveCount(0); // no delete without a server
  const lanes = page.getByTestId("lanes");
  await expect(lanes).toBeVisible();
  const box = await lanes.boundingBox();
  expect(box!.width).toBeGreaterThan(600);
  expect(box!.height).toBeGreaterThan(400);
  // canvas actually has ink on it
  const inked = await lanes.evaluate((c: HTMLCanvasElement) => {
    const d = c.getContext("2d")!.getImageData(0, 0, c.width, c.height).data;
    let n = 0; for (let i = 3; i < d.length; i += 4 * 97) if (d[i] > 0) n++;
    return n;
  });
  expect(inked).toBeGreaterThan(1000);
  await expect(page.locator(".title")).toContainText(DEMO_TITLE);

  const before = await strata(page);
  await page.getByRole("button", { name: "Play" }).click();
  await expect.poll(async () => (await strata(page)).t, { timeout: 1500, intervals: [100] }).toBeGreaterThan(before.t + 0.05);
  const after = await strata(page);
  expect(after.x).toBeGreaterThan(before.x);
  expect(after.playing).toBe(true);

  await page.getByRole("button", { name: "visualizer" }).click();
  await expect(page.locator(".viz")).toBeVisible();
  await expect(page.getByTestId("orbs")).toBeVisible();
  expect(await page.getByTestId("orbs").evaluate((c: HTMLCanvasElement) => c.getContext("webgl2") !== null)).toBe(true);
  expect((await strata(page)).gl).toBe(true);
  // the overlay actually draws labels/values
  const ink = await page.locator(".viz-orbs-o").evaluate((c: HTMLCanvasElement) => {
    const d = c.getContext("2d")!.getImageData(0, 0, c.width, c.height).data;
    let n = 0; for (let i = 3; i < d.length; i += 4 * 101) if (d[i] > 0) n++;
    return n;
  });
  expect(ink).toBeGreaterThan(200);
  await page.keyboard.press("Escape");
  await expect(page.locator(".viz")).toBeHidden();

  expect(errors, errors.join("\n")).toEqual([]);
});

test("screenshots: zoomed out, zoomed in, visualizer", async ({ page }) => {
  const errors: string[] = [];
  await boot(page, errors);
  // hover mid-chorus so the inspector is populated
  const lanes = page.getByTestId("lanes");
  const box = (await lanes.boundingBox())!;
  await page.mouse.move(box.x + 136 + (box.width - 136) * (50 / 176), box.y + 200);
  await page.waitForTimeout(150);
  await page.screenshot({ path: `${SHOTS}/timeline-zoomed-out.png` });

  // zoom around the chorus entrance with ctrl+wheel
  const x = box.x + 136 + (box.width - 136) * (41.9 / 176);
  await page.mouse.move(x, box.y + 200);
  for (let i = 0; i < 7; i++) { await page.keyboard.down("Control"); await page.mouse.wheel(0, -120); await page.keyboard.up("Control"); }
  await page.mouse.move(x + 40, box.y + 330);
  await page.waitForTimeout(150);
  await page.screenshot({ path: `${SHOTS}/timeline-zoomed-in.png` });

  // visualizer: seek just before the demo drop (0:15.7) and let it run so kicks/hats are live
  await page.evaluate(() => (window as unknown as { __strata: S & { seek: (t: number) => void } }).__strata.seek(15.2));
  await page.keyboard.press("v");
  await page.mouse.move(5, 5);
  await page.keyboard.press("Space");
  await page.waitForTimeout(900);
  await page.screenshot({ path: `${SHOTS}/visualizer.png` });
  await page.keyboard.press("Space");
  expect(errors, errors.join("\n")).toEqual([]);
});

test("report template renders read-only from injected JSON", async ({ page }) => {
  const { writeFileSync } = await import("node:fs");
  const tpl = readFileSync(resolve(import.meta.dirname, "../../strata/web/report_template.html"), "utf8");
  expect(tpl).toContain('<script id="strata-data" type="application/json">__STRATA_DATA__</script>');
  const json = readFileSync(resolve(import.meta.dirname, "../public/demo/sample_analysis.json"), "utf8").replace(/<\//g, "<\\/");
  const out = resolve(import.meta.dirname, "../test-results/report.html");
  mkdirSync(resolve(out, ".."), { recursive: true });
  writeFileSync(out, tpl.replace("__STRATA_DATA__", () => json));
  const errors: string[] = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.goto(`file://${out}`);
  await page.waitForSelector("body[data-ready='1']", { timeout: 15_000 });
  await expect(page.getByTestId("lanes")).toBeVisible();
  await expect(page.locator(".title")).toContainText(DEMO_TITLE);
  await expect(page.locator(".tp-play")).toBeHidden(); // no audio → no transport
  await page.screenshot({ path: `${SHOTS}/report.png` });
  expect(errors, errors.join("\n")).toEqual([]);
});

test("library delete: inline confirm, keyboard, errors, next track, empty state (mocked server)", async ({ page }) => {
  // Fake STRATA server: nothing real is ever deleted.
  const demo = readFileSync(resolve(import.meta.dirname, "../public/demo/sample_analysis.json"), "utf8");
  let tracks = [
    { id: "aaaa000000000001", title: "Track A", duration: 100, bpm: 120, key: "C minor", created: "2026-10-10T00:00:00Z" },
    { id: "bbbb000000000002", title: "Track B", duration: 90, bpm: 90, key: "D major", created: "2026-10-10T00:00:00Z" },
  ];
  const deletes: string[] = [];
  let failNext = false;
  await page.routeWebSocket("**/api/transport", () => { /* accept and ignore */ });
  await page.route("**/api/**", async (route) => {
    const req = route.request();
    const path = new URL(req.url()).pathname;
    const m = /^\/api\/tracks\/([^/]+)(\/audio)?$/.exec(path);
    if (path === "/api/tracks") return route.fulfill({ json: tracks });
    if (m && req.method() === "DELETE") {
      if (failNext) { failNext = false; return route.fulfill({ status: 500, json: { ok: false, error: "disk is read-only" } }); }
      deletes.push(m[1]);
      tracks = tracks.filter((t) => t.id !== m[1]);
      return route.fulfill({ json: { ok: true, deleted: m[1] } });
    }
    if (m && m[2]) return route.fulfill({ path: resolve(import.meta.dirname, "../public/demo/audio.mp3"), contentType: "audio/mpeg" });
    if (m) {
      const a = JSON.parse(demo);
      const t = tracks.find((x) => x.id === m[1])!;
      a.track = { ...a.track, id: t.id, title: t.title };
      return route.fulfill({ json: a });
    }
    return route.fulfill({ status: 204 });
  });
  const errors: string[] = [];
  page.on("console", (m) => { if (m.type() === "error" && !/status of 500/.test(m.text())) errors.push(m.text()); });
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.goto("/");
  await page.waitForSelector("body[data-ready='1']");
  await expect(page.locator(".title")).toHaveText("Track A");

  const rowA = page.locator('li[data-row="aaaa000000000001"]');
  const removeA = rowA.getByRole("button", { name: /Remove Track A/ });
  await expect(removeA).toHaveCSS("opacity", "0");
  await rowA.hover();
  await expect(removeA).toHaveCSS("opacity", "1");
  await removeA.click();
  await expect(rowA.getByText("Remove from library? Your audio file stays.")).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/library-confirm.png`, clip: { x: 0, y: 80, width: 420, height: 260 } });
  await rowA.getByRole("button", { name: "Cancel" }).click();
  await expect(rowA.getByText("Remove from library?")).toHaveCount(0);
  expect(deletes).toEqual([]);

  // keyboard: Delete on the focused track, Escape cancels, then confirm for real
  await rowA.locator(".trk").focus();
  await page.keyboard.press("Delete");
  await expect(rowA.locator(".trk-confirm")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(rowA.locator(".trk-confirm")).toHaveCount(0);
  await rowA.locator(".trk").focus();
  await page.keyboard.press("Backspace");
  await rowA.getByRole("button", { name: "Remove", exact: true }).click();
  await expect(rowA).toHaveCount(0);
  expect(deletes).toEqual(["aaaa000000000001"]);
  // the open track was removed, so the next one opens
  await expect(page.locator(".title")).toHaveText("Track B");
  await expect(page.locator('.trk[data-id="bbbb000000000002"]')).toHaveAttribute("aria-current", "true");

  // server error is shown inline and nothing is removed
  failNext = true;
  const rowB = page.locator('li[data-row="bbbb000000000002"]');
  await rowB.hover();
  await rowB.getByRole("button", { name: /Remove Track B/ }).click();
  await rowB.getByRole("button", { name: "Remove", exact: true }).click();
  await expect(rowB.getByRole("alert")).toContainText("disk is read-only");
  await expect(rowB).toHaveCount(1);

  // retry succeeds → empty state
  await rowB.hover();
  await rowB.getByRole("button", { name: /Remove Track B/ }).click();
  await rowB.getByRole("button", { name: "Remove", exact: true }).click();
  await expect(rowB).toHaveCount(0);
  expect(deletes).toEqual(["aaaa000000000001", "bbbb000000000002"]);
  await expect(page.locator(".title")).toHaveText("Drop a track to begin");
  await expect(page.locator(".lib-empty")).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/library-empty.png` });
  expect(errors, errors.join("\n")).toEqual([]);
});
