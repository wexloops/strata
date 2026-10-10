import "./fonts";
import "./style.css";
import { fontsReady } from "./fonts";
import { Api } from "./api";
import { App } from "./app";

declare global { interface Window { __strata?: unknown } }

(async () => {
  await fontsReady();
  const api = new Api();
  await api.init();
  const app = new App(document.getElementById("app")!, { api, report: false });
  window.__strata = {
    mode: api.mode,
    time: () => app.transport.time(),
    playing: () => app.transport.playing,
    playheadX: () => app.timeline.view.x(app.transport.time()),
    webgl2: () => !!app.orbs.gl,
    seek: (t: number) => app.transport.seek(t),
  };
  const tracks = await app.library!.refresh();
  const wanted = new URLSearchParams(location.search).get("track");
  const first = tracks.find((t) => t.id === wanted) ?? tracks[0];
  if (first) await app.open(first.id);
  else document.querySelector(".title")!.textContent = api.mode === "offline" ? "No server found" : "Drop a track to begin";
  document.body.dataset.ready = "1";
})();
