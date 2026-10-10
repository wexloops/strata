// Read-only single-file report. The Python exporter replaces __STRATA_DATA__ in
// <script id="strata-data" type="application/json"> with the analysis JSON.
// Optional audio: set data-audio="<url>" on that script tag; without it (or if it fails to load)
// the transport is hidden and the timeline stays fully inspectable.
import "./fonts";
import "./style.css";
import { fontsReady } from "./fonts";
import { App } from "./app";
import { normalize } from "./types";

(async () => {
  await fontsReady();
  const root = document.getElementById("app")!;
  const tag = document.getElementById("strata-data");
  let data: unknown = null;
  try { data = JSON.parse(tag?.textContent || ""); } catch { /* placeholder not replaced */ }
  if (!data || typeof data !== "object") {
    root.innerHTML = `<p class="empty-report">This report has no analysis data. Generate it with <code>strata export &lt;track&gt; --format report</code>.</p>`;
    return;
  }
  const app = new App(root, { api: null, report: true });
  await app.load(normalize(data), tag?.dataset.audio || null);
  document.body.dataset.ready = "1";
})();
