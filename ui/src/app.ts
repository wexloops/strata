// App shell shared by the live UI (main.ts) and the read-only report (report.ts).
import type { Analysis } from "./types";
import type { Api } from "./api";
import { Transport } from "./transport";
import { Timeline } from "./timeline/timeline";
import { Inspector } from "./inspector";
import { OrbsViz } from "./orbs";
import { Library } from "./panels/library";
import { ExportPanel } from "./panels/export";
import { LivePanel } from "./panels/live";
import { momentAt, fmtTime } from "./query";
import { sectionColor } from "./colors";

const esc = (s: string) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);

const GLYPH = `<svg class="glyph" viewBox="0 0 22 22" aria-hidden="true">
  <rect x="0" y="2" width="22" height="2.4" fill="#5B6CFF"/><rect x="4" y="6.4" width="18" height="2.4" fill="#2EC4B6"/>
  <rect x="0" y="10.8" width="14" height="2.4" fill="#FF3D7F"/><rect x="8" y="15.2" width="14" height="2.4" fill="#B45CFF"/>
  <rect x="0" y="19.6" width="22" height="2.4" fill="#F5F5F0"/></svg>`;

export interface AppOptions { api: Api | null; report: boolean; }

export class App {
  readonly transport = new Transport();
  readonly timeline: Timeline;
  readonly inspector: Inspector;
  readonly orbs: OrbsViz;
  a: Analysis | null = null;
  trackId = "";
  library: Library | null = null;
  private exportP: ExportPanel | null = null;
  private liveP: LivePanel | null = null;
  private root: HTMLElement;
  private vizOpen = false;
  private hasAudio = false;
  private $ = <T extends HTMLElement>(s: string) => this.root.querySelector<T>(s)!;
  private lastTc = "";

  constructor(root: HTMLElement, private opts: AppOptions) {
    this.root = root;
    root.className = `app ${opts.report ? "is-report" : ""}`;
    root.innerHTML = `
      <header class="hdr">
        <div class="brand">${GLYPH}<span>STRATA</span></div>
        <div class="ttl"><h1 class="title">&nbsp;</h1><div class="sub"></div></div>
        <dl class="ro"></dl>
        <div class="flags"></div>
      </header>
      ${opts.report ? "" : `<aside class="lib" aria-label="Library"></aside>`}
      <main class="main">
        <div class="tp" role="toolbar" aria-label="Transport">
          <button class="tp-play" aria-label="Play" title="Play / pause (space)"><svg viewBox="0 0 16 16"><path class="i-play" d="M4 2.5v11l9-5.5z"/><g class="i-pause"><rect x="3.5" y="2.5" width="3" height="11"/><rect x="9.5" y="2.5" width="3" height="11"/></g></svg></button>
          <div class="tp-tc" aria-live="off"><span class="tc">00:00.000</span><span class="tc-d"></span></div>
          <div class="tp-bb"><span class="k">bar.beat</span><span class="v bb">–</span></div>
          <div class="tp-sec"><i></i><span class="v sec">–</span></div>
          <div class="tp-chord"><span class="k">chord</span><span class="v chd">–</span></div>
          <div class="tp-sp"></div>
          <span class="tp-silent" hidden title="No audio is driving the clock">silent clock</span>
          <div class="tp-zoom">
            <button data-z="out" aria-label="Zoom out" title="Zoom out (−)">−</button>
            <button data-z="fit" title="Fit whole track (0)">fit</button>
            <button data-z="in" aria-label="Zoom in" title="Zoom in (+)">+</button>
          </div>
          <button class="tp-follow on" aria-pressed="true" title="Follow the playhead (F)">follow</button>
          <button class="tp-viz" title="Visualizer (V)">visualizer</button>
        </div>
        <div class="tl-host"></div>
        <div class="hint"><span><kbd>ctrl</kbd>/<kbd>⌘</kbd> + wheel or pinch zooms at the cursor</span><span>wheel or drag scrolls</span><span>click seeks</span><span>click a lane name to fold it</span><span class="h-audio"><kbd>space</kbd> play</span><span class="h-audio"><kbd>V</kbd> visualizer</span></div>
      </main>
      <aside class="side">
        <div class="tabs" role="tablist">
          <button role="tab" data-tab="insp" aria-selected="true">inspect</button>
          ${opts.report ? "" : `<button role="tab" data-tab="exp" aria-selected="false">export</button><button role="tab" data-tab="live" aria-selected="false">live</button>`}
        </div>
        <div class="tab-p" data-p="insp"></div>
        ${opts.report ? "" : `<div class="tab-p" data-p="exp" hidden></div><div class="tab-p" data-p="live" hidden></div>`}
      </aside>
      <section class="viz" hidden aria-label="Visualizer">
        <canvas class="viz-orbs" data-testid="orbs"></canvas>
        <canvas class="viz-orbs-o" aria-hidden="true"></canvas>
        <button class="viz-x" title="Close (Esc)">close</button>
        <div class="viz-err" hidden></div>
      </section>`;

    this.timeline = new Timeline(this.$(".tl-host"));
    this.inspector = new Inspector(this.$('[data-p="insp"]'));
    this.orbs = new OrbsViz(this.$<HTMLCanvasElement>(".viz-orbs"), this.$<HTMLCanvasElement>(".viz-orbs-o"));
    if (!opts.report && opts.api) {
      this.library = new Library(this.$(".lib"), opts.api);
      this.library.onOpen = (id) => void this.open(id);
      this.library.onDeleted = (id, next) => {
        if (id !== this.trackId) return;
        if (next) void this.open(next);
        else this.clear();
      };
      this.exportP = new ExportPanel(this.$('[data-p="exp"]'), opts.api);
      this.liveP = new LivePanel(this.$('[data-p="live"]'), opts.api);
      this.transport.on((e) => opts.api!.transport(e.op, e.t));
    }
    this.timeline.onSeek = (t) => { this.transport.seek(t); };
    this.timeline.onHover = () => {};
    this.timeline.onUserView = () => this.syncFollow();
    this.bind();
    requestAnimationFrame(this.loop);
  }

  async open(id: string): Promise<void> {
    if (!this.opts.api) return;
    try {
      const a = await this.opts.api.getTrack(id);
      this.trackId = id;
      this.library?.setActive(id);
      await this.load(a, this.opts.api.audioUrl(id));
    } catch (e) {
      this.$(".sub").textContent = (e as Error).message;
    }
  }

  /** Empty state: nothing in the library. */
  clear(): void {
    this.transport.pause();
    void this.transport.load(null, 0);
    this.a = null;
    this.trackId = "";
    this.setViz(false);
    this.root.classList.add("is-empty");
    this.$(".title").textContent = "Drop a track to begin";
    this.$(".sub").textContent = "Your library is empty. Drop an audio file on the left to analyze it.";
    this.$(".ro").innerHTML = "";
    this.$(".flags").innerHTML = "";
    document.title = "STRATA";
  }

  async load(a: Analysis, audio: string | null): Promise<void> {
    this.root.classList.remove("is-empty");
    this.a = a;
    this.lastTc = "";
    this.inspector.reset();
    this.header(a);
    this.timeline.setAnalysis(a);
    this.exportP?.render(a, this.trackId);
    this.liveP?.render(a, this.trackId);
    this.hasAudio = await this.transport.load(audio, a.track.duration);
    if (this.opts.report && !this.hasAudio) this.root.classList.add("no-audio");
  }

  private header(a: Analysis): void {
    const t = a.track;
    this.$(".title").textContent = t.title || t.id;
    document.title = `${t.title || t.id}  STRATA`;
    const created = a.strata.created ? new Date(a.strata.created) : null;
    this.$(".sub").textContent = [
      `${fmtTime(t.duration, false)}`, `${(t.sample_rate / 1000).toFixed(1)} kHz`, t.channels === 1 ? "mono" : `${t.channels} ch`,
      created && !isNaN(+created) ? created.toISOString().slice(0, 10) : "", `strata ${a.strata.version}`,
    ].filter(Boolean).join("   ");
    const alt = a.tempo.alternatives?.[0];
    const ro: [string, string, string?][] = [
      [a.tempo.bpm ? a.tempo.bpm.toFixed(1) : "–", "bpm", alt ? `alt ${alt.bpm.toFixed(1)}` : a.tempo.stable ? "stable" : "drifts"],
      [`${a.tempo.meter}/4`, "meter"],
      [a.key.label || "–", "key", a.key.camelot],
      [a.dynamics.lufs ? `${a.dynamics.lufs.toFixed(1).replace("-", "−")}` : "–", "LUFS", `LRA ${a.dynamics.lra.toFixed(1)}`],
    ];
    this.$(".ro").innerHTML = ro.map(([v, k, x]) => `<div><dt>${k}${x ? ` <em>${esc(x)}</em>` : ""}</dt><dd>${esc(v)}</dd></div>`).join("")
      + `<div class="prof ${a.strata.profile === "commercial-safe" ? "safe" : ""}"><dt>profile</dt><dd>${esc(a.strata.profile)}</dd></div>`;
    const nc = a.provenance.filter((p) => p.nc && p.ok);
    // Not installed / deliberately disabled is a choice, not a failure: show it muted.
    const skipped = (p: Analysis["provenance"][number]) => /^(not installed|disabled)/.test(p.error ?? "");
    const failed = a.provenance.filter((p) => !p.ok && !skipped(p));
    const off = a.provenance.filter((p) => !p.ok && skipped(p));
    this.$(".flags").innerHTML =
      nc.map((p) => `<span class="flag nc" title="${esc(p.license)}: non-commercial weights. Excluded under --profile commercial-safe.">nc ${esc(p.backend)}</span>`).join("")
      + failed.map((p) => `<span class="flag fail" title="${esc(p.error ?? "")}">${esc(p.backend)} failed</span>`).join("")
      + off.map((p) => `<span class="flag off" title="${esc(p.error ?? "")}">${esc(p.backend)} off</span>`).join("");
  }

  private syncFollow(): void {
    const b = this.$(".tp-follow");
    b.classList.toggle("on", this.timeline.view.follow);
    b.setAttribute("aria-pressed", String(this.timeline.view.follow));
  }

  private bind(): void {
    this.$(".tp-play").addEventListener("click", () => this.togglePlay());
    this.$(".tp-follow").addEventListener("click", () => { this.timeline.view.follow = !this.timeline.view.follow; this.syncFollow(); });
    this.$(".tp-viz").addEventListener("click", () => this.setViz(true));
    this.$(".viz-x").addEventListener("click", () => this.setViz(false));
    this.root.querySelectorAll<HTMLButtonElement>(".tp-zoom button").forEach((b) => b.addEventListener("click", () => this.zoom(b.dataset.z!)));
    this.root.querySelectorAll<HTMLButtonElement>('[role="tab"]').forEach((b) => b.addEventListener("click", () => {
      this.root.querySelectorAll<HTMLButtonElement>('[role="tab"]').forEach((x) => x.setAttribute("aria-selected", String(x === b)));
      this.root.querySelectorAll<HTMLElement>(".tab-p").forEach((p) => { p.hidden = p.dataset.p !== b.dataset.tab; });
    }));
    this.$(".viz-orbs-o").addEventListener("click", () => this.togglePlay());
    window.addEventListener("keydown", (e) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA" || e.metaKey || e.ctrlKey || e.altKey) return;
      if (!this.a) return;
      const k = e.key;
      if (k === " ") { e.preventDefault(); if ((e.target as HTMLElement)?.tagName === "BUTTON") (e.target as HTMLElement).blur(); this.togglePlay(); }
      else if (k === "v" || k === "V") this.setViz(!this.vizOpen);
      else if (k === "Escape" && this.vizOpen) this.setViz(false);
      else if (k === "f" || k === "F") { this.timeline.view.follow = !this.timeline.view.follow; this.syncFollow(); }
      else if (k === "0") this.zoom("fit");
      else if (k === "+" || k === "=") this.zoom("in");
      else if (k === "-" || k === "_") this.zoom("out");
      else if (k === "Home") this.transport.seek(0);
      else if (k === "ArrowRight" || k === "ArrowLeft") { e.preventDefault(); this.step(k === "ArrowRight" ? 1 : -1, e.shiftKey); }
    });
  }

  private step(dir: number, section: boolean): void {
    const a = this.a!;
    const t = this.transport.time();
    const marks = section ? a.sections.map((s) => s.start) : a.bars.map((b) => b.start);
    const eps = 0.05;
    const next = dir > 0 ? marks.find((m) => m > t + eps) : [...marks].reverse().find((m) => m < t - eps);
    this.transport.seek(next ?? (dir > 0 ? a.track.duration : 0));
  }

  private zoom(z: string): void {
    const v = this.timeline.view;
    const anchor = v.x(this.transport.time());
    const ax = anchor >= 136 && anchor <= 136 + v.plotW ? anchor : 136 + v.plotW / 2;
    if (z === "fit") v.fit(); else v.zoomAt(z === "in" ? 1.6 : 1 / 1.6, ax);
  }

  togglePlay(): void {
    if (!this.a || (this.opts.report && !this.hasAudio)) return;
    if (!this.transport.playing) { this.timeline.view.follow = true; this.syncFollow(); }
    this.transport.toggle();
  }

  setViz(on: boolean): void {
    if (on && this.opts.report && !this.hasAudio && !this.a) return;
    this.vizOpen = on;
    const v = this.$(".viz");
    v.hidden = !on;
    document.body.classList.toggle("viz-on", on);
    this.showVizError();
  }

  private showVizError(): void {
    const err = this.orbs.error;
    const e = this.$(".viz-err");
    e.hidden = !(this.vizOpen && err);
    e.textContent = err ?? "";
  }

  private loop = (): void => {
    requestAnimationFrame(this.loop);
    const a = this.a;
    if (!a) return;
    const t = this.transport.time();
    const playing = this.transport.playing;
    this.timeline.frame(t, playing);
    this.root.classList.toggle("playing", playing);
    this.$(".tp-silent").hidden = !(playing && this.transport.silent) || this.opts.report;
    const tc = fmtTime(t);
    if (tc !== this.lastTc) {
      this.lastTc = tc;
      const m = momentAt(a, t);
      this.$(".tc").textContent = tc;
      this.$(".tc").dataset.t = t.toFixed(3);
      this.$(".tc-d").textContent = `/ ${fmtTime(a.track.duration, false)}`;
      this.$(".bb").textContent = m.beat ? `${m.beat.bar}.${m.beat.beat}` : "–";
      this.$(".sec").textContent = m.section ? m.section.label : "–";
      this.$<HTMLElement>(".tp-sec i").style.background = m.section ? sectionColor(m.section) : "transparent";
      this.$(".chd").textContent = m.chord ? m.chord.label : "–";
    }
    const hov = this.timeline.hoverT;
    this.inspector.render(a, hov ?? t, hov !== null ? "hover" : "playhead");
    if (this.vizOpen) {
      const m = momentAt(a, t);
      this.orbs.frame(a, m);
    }
  };
}

