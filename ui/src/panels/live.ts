// LIVE: the server's 60 Hz OSC clock follows this transport (spec §9).
import type { Api } from "../api";
import type { Analysis } from "../types";

const esc = (s: string) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);

const CONTINUOUS: [string, string, string][] = [
  ["/strata/time", "f", "seconds"],
  ["/strata/beat/phase", "f", "0..1 within the beat"],
  ["/strata/bar/phase", "f", "0..1 within the bar"],
  ["/strata/section/progress", "f", "0..1 within the section"],
];
const EDGES: [string, string, string][] = [
  ["/strata/beat", "i", "beat number"],
  ["/strata/downbeat", "i", "bar number"],
  ["/strata/bar", "i", "bar number"],
  ["/strata/section", "s i", "label, index"],
  ["/strata/chord", "s", "chord label"],
  ["/strata/kick", "f", "strength"],
  ["/strata/snare", "f", "strength"],
  ["/strata/hat", "f", "strength"],
  ["/strata/drop", "f", "strength"],
  ["/strata/cue", "s f", "type, strength"],
];
const INPUT: [string, string, string][] = [
  ["/strata/play", "", "start the clock"],
  ["/strata/pause", "", "stop the clock"],
  ["/strata/seek", "f", "jump to seconds"],
];

export class LivePanel {
  private on = false;
  private id = "";
  constructor(private el: HTMLElement, private api: Api) { el.classList.add("live"); }

  render(a: Analysis, id: string): void {
    this.id = id;
    const host = localStorage.getItem("strata.osc.host") || "127.0.0.1";
    const port = localStorage.getItem("strata.osc.port") || "9000";
    const server = this.api.mode === "server";
    const tbl = (rows: [string, string, string][]) => rows.map(([a, t, d]) => `<tr><td class="addr">${a}</td><td class="ty">${t}</td><td>${d}</td></tr>`).join("");
    const curves = a.curves.names.map((n) => `<span>${esc(n)}</span>`).join("");
    this.el.innerHTML = `
      <p class="p-lede">Sends OSC at 60 Hz, locked to this playhead. Play, pause and seek here and the clock follows.</p>
      <form class="live-f">
        <label>host<input name="host" value="${esc(host)}" autocomplete="off" spellcheck="false"></label>
        <label>port<input name="port" value="${esc(port)}" inputmode="numeric" pattern="[0-9]*"></label>
        <button type="submit" class="live-go" ${server ? "" : "disabled"}>${this.on ? "Stop OSC" : "Start OSC"}</button>
      </form>
      <p class="live-st" role="status">${server ? (this.on ? `Sending to ${esc(host)}:${esc(port)}` : "Off") : "Live OSC needs the STRATA server. Run <code>strata serve</code>."}</p>
      <h3>every tick</h3><table>${tbl(CONTINUOUS)}<tr><td class="addr">/strata/curve/&lt;name&gt;</td><td class="ty">f</td><td>0..1</td></tr></table>
      <div class="live-curves">${curves}</div>
      <h3>on each event</h3><table>${tbl(EDGES)}</table>
      <h3>listens for</h3><table>${tbl(INPUT)}</table>
      <p class="p-note">Headless: <code>strata live &lt;track&gt; --osc ${esc(host)}:${esc(port)}</code></p>`;
    const form = this.el.querySelector<HTMLFormElement>(".live-f")!;
    const st = this.el.querySelector<HTMLElement>(".live-st")!;
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(form);
      const h = String(fd.get("host") || "").trim();
      const p = Number(fd.get("port"));
      if (!h || !Number.isInteger(p) || p < 1 || p > 65535) { st.textContent = "Enter a host and a port between 1 and 65535."; st.className = "live-st err"; return; }
      localStorage.setItem("strata.osc.host", h); localStorage.setItem("strata.osc.port", String(p));
      const want = !this.on;
      try {
        await this.api.live(this.id, h, p, want);
        this.on = want;
        this.render(a, this.id);
      } catch (err) {
        st.textContent = (err as Error).message; st.className = "live-st err";
      }
    });
  }
}
