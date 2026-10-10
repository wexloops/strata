// Timeline: stacked lanes on one base canvas (redrawn only when the view changes) plus an overlay
// canvas for playhead/hover (redrawn every frame), and a minimap overview.
import type { Analysis } from "../types";
import { fmtTime } from "../query";
import { sectionColor, rgba } from "../colors";
import { View, GUTTER } from "./view";
import { type Lane, type LaneCtx, laneHeight, MONO, HAIR, DIM, text, curveMax } from "./lane";
import { ruler } from "./ruler";
import { sectionsLane } from "./sections";
import { waveformLane } from "./waveform";
import { beatsLane } from "./beats";
import { chordsLane } from "./chords";
import { drumsLane } from "./drums";
import { notesLane } from "./notes";
import { energyLane } from "./energy";
import { cuesLane } from "./cues";
import { agreementLane } from "./agreement";

export const LANES: Lane[] = [sectionsLane, waveformLane, beatsLane, chordsLane, drumsLane, notesLane, energyLane, cuesLane, agreementLane];
const COLLAPSED = 20;
const PAD = 8; // vertical padding inside each expanded lane
const STORE = "strata.collapsed";

interface Placed { lane: Lane; y: number; h: number; collapsed: boolean; }

export class Timeline {
  readonly view = new View();
  a: Analysis | null = null;
  onSeek: (t: number) => void = () => {};
  onHover: (t: number | null) => void = () => {};
  onUserView: () => void = () => {};
  hoverT: number | null = null;


  private scroller: HTMLElement;
  private stack: HTMLElement;
  private base: HTMLCanvasElement;
  private over: HTMLCanvasElement;
  private mini: HTMLCanvasElement;
  private miniBg: HTMLCanvasElement = document.createElement("canvas");
  private placed: Placed[] = [];
  private collapsed: Set<string>;
  private drawnVersion = -1;
  private dpr = 1;
  private width = 0;
  private totalH = 0;
  private miniDirty = true;
  private playT = 0;

  constructor(root: HTMLElement) {

    root.classList.add("timeline");
    root.innerHTML = `
      <div class="tl-scroll"><div class="tl-stack">
        <canvas class="tl-base" aria-label="Analysis lanes" data-testid="lanes"></canvas>
        <canvas class="tl-over" aria-hidden="true"></canvas>
      </div></div>
      <div class="tl-mini-wrap"><canvas class="tl-mini" aria-label="Overview minimap"></canvas></div>`;
    this.scroller = root.querySelector(".tl-scroll")!;
    this.stack = root.querySelector(".tl-stack")!;
    this.base = root.querySelector(".tl-base")!;
    this.over = root.querySelector(".tl-over")!;
    this.mini = root.querySelector(".tl-mini")!;
    let saved: string[] = [];
    try { saved = JSON.parse(localStorage.getItem(STORE) || "[]"); } catch { /* ignore */ }
    this.collapsed = new Set(saved);
    new ResizeObserver(() => this.resize()).observe(this.scroller);
    this.bind();
  }

  setAnalysis(a: Analysis): void {
    this.a = a;
    this.view.duration = a.track.duration;
    this.resize();
    this.view.fit();
    this.miniDirty = true;
    this.drawnVersion = -1;
  }

  private layout(): void {
    if (!this.a) return;
    let y = 0;
    this.placed = [];
    for (const lane of [ruler, ...LANES]) {
      const collapsed = lane !== ruler && this.collapsed.has(lane.id);
      const h = collapsed ? COLLAPSED : laneHeight(lane, this.a) + (lane === ruler ? 0 : PAD * 2);
      this.placed.push({ lane, y, h, collapsed });
      y += h;
    }
    this.totalH = y;
  }

  private resize(): void {
    const w = this.scroller.clientWidth;
    if (!w) return;
    this.dpr = Math.min(2, window.devicePixelRatio || 1);
    this.width = w;
    this.layout();
    const H = Math.max(this.totalH, 1);
    this.stack.style.height = `${H}px`;
    for (const c of [this.base, this.over]) {
      c.width = Math.round(w * this.dpr); c.height = Math.round(H * this.dpr);
      c.style.width = `${w}px`; c.style.height = `${H}px`;
    }
    const mw = Math.max(50, this.mini.parentElement!.clientWidth - GUTTER), mh = 44;
    this.mini.width = Math.round(mw * this.dpr); this.mini.height = Math.round(mh * this.dpr);
    this.mini.style.width = `${mw}px`; this.mini.style.height = `${mh}px`;
    this.view.setWidth(w);
    this.miniDirty = true;
    this.drawnVersion = -1;
  }

  toggleLane(id: string): void {
    this.collapsed.has(id) ? this.collapsed.delete(id) : this.collapsed.add(id);
    localStorage.setItem(STORE, JSON.stringify([...this.collapsed]));
    this.resize();
  }

  /** Called every animation frame. */
  frame(t: number, playing: boolean): void {
    if (!this.a) return;
    this.playT = t;
    const v = this.view;
    if (playing && v.follow) {
      const x = v.x(t);
      if (x < GUTTER || x > GUTTER + v.plotW * 0.86) v.showAt(t, 0.14);
    }
    if (this.drawnVersion !== v.version) { this.drawBase(); this.drawnVersion = v.version; }
    this.drawOverlay();
    this.drawMini();
  }

  private drawBase(): void {
    const a = this.a!;
    const ctx = this.base.getContext("2d")!;
    const d = this.dpr;
    ctx.setTransform(d, 0, 0, d, 0, 0);
    ctx.clearRect(0, 0, this.width, this.totalH);
    const x0 = GUTTER, x1 = this.width;
    for (const p of this.placed) {
      const c: LaneCtx = { ctx, a, view: this.view, y: p.y + (p.lane === ruler ? 0 : PAD), h: p.h - (p.lane === ruler ? 0 : PAD * 2), x0, x1 };
      if (!p.collapsed) {
        ctx.save();
        ctx.beginPath(); ctx.rect(x0, p.y, x1 - x0, p.h); ctx.clip();
        p.lane.draw(c);
        ctx.restore();
      }
      // gutter
      ctx.fillStyle = "#000";
      ctx.fillRect(0, p.y, GUTTER, p.h);
      if (p.lane !== ruler) {
        const caret = p.collapsed ? "▸" : "▾";
        text(ctx, caret, 4, p.y + 11, `9px ${MONO}`, "rgba(245,245,240,0.35)");
        text(ctx, p.lane.name, 14, p.y + 11, `600 10.5px ${MONO}`, "rgba(245,245,240,0.9)");
        if (!p.collapsed) {
          const note = p.lane.note?.(a);
          if (note && !p.lane.gutter) text(ctx, note, 14, p.y + 25, `9.5px ${MONO}`, DIM);
          if (p.lane.gutter) p.lane.gutter(c);
        } else {
          const note = p.lane.note?.(a);
          if (note) text(ctx, note, x0 + 8, p.y + 10, `9.5px ${MONO}`, "rgba(245,245,240,0.28)");
        }
      } else {
        text(ctx, "t", 14, p.y + 9, `600 10.5px ${MONO}`, "rgba(245,245,240,0.5)");
      }
      ctx.fillStyle = HAIR;
      ctx.fillRect(0, p.y + p.h - 1, this.width, 1);
    }
    ctx.fillStyle = "rgba(245,245,240,0.16)";
    ctx.fillRect(GUTTER - 1, 0, 1, this.totalH);
  }

  private drawOverlay(): void {
    const ctx = this.over.getContext("2d")!;
    const d = this.dpr;
    ctx.setTransform(d, 0, 0, d, 0, 0);
    ctx.clearRect(0, 0, this.width, this.totalH);
    const v = this.view;
    if (this.hoverT !== null) {
      const x = Math.round(v.x(this.hoverT)) + 0.5;
      if (x >= GUTTER) {
        ctx.fillStyle = "rgba(245,245,240,0.28)";
        for (let y = 24; y < this.totalH; y += 4) ctx.fillRect(x, y, 1, 2);
        const lab = fmtTime(this.hoverT);
        ctx.font = `10px ${MONO}`;
        const w = ctx.measureText(lab).width + 10;
        const bx = Math.min(x + 1, this.width - w);
        ctx.fillStyle = "#F5F5F0";
        ctx.fillRect(bx, 3, w, 17);
        text(ctx, lab, bx + 5, 12, `10px ${MONO}`, "#000");
      }
    }
    const px = v.x(this.playT);
    if (px >= GUTTER - 1 && px <= this.width + 1) {
      const x = Math.round(px);
      ctx.fillStyle = "rgba(245,245,240,0.10)";
      ctx.fillRect(x - 3, 0, 7, this.totalH);
      ctx.fillStyle = "#F5F5F0";
      ctx.fillRect(x, 0, 1.5, this.totalH);
      ctx.beginPath(); ctx.moveTo(x - 5, 0); ctx.lineTo(x + 6.5, 0); ctx.lineTo(x + 0.75, 7); ctx.closePath(); ctx.fill();
    }
  }

  private drawMini(): void {
    const a = this.a!;
    const d = this.dpr;
    const W = this.mini.width / d, H = this.mini.height / d;
    if (this.miniDirty) {
      this.miniBg.width = this.mini.width; this.miniBg.height = this.mini.height;
      const g = this.miniBg.getContext("2d")!;
      g.setTransform(d, 0, 0, d, 0, 0);
      const dur = a.track.duration;
      const sx = (t: number) => (t / dur) * W;
      const ld = a.curves.data.loudness ?? a.curves.data.rms;
      for (const s of a.sections) {
        const xa = sx(s.start), xb = sx(s.end);
        const col = sectionColor(s);
        g.fillStyle = rgba(col, 0.9);
        g.fillRect(xa, 0, Math.max(1, xb - xa - 1), 6);
        for (let x = Math.floor(xa); x < xb; x++) {
          const v = curveMax(ld, a.curves.fps, (x / W) * dur, ((x + 1) / W) * dur);
          const hh = Math.max(1, v * (H - 12));
          g.fillStyle = rgba(col, 0.55);
          g.fillRect(x, H - hh, 1, hh);
        }
      }
      this.miniDirty = false;
    }
    const ctx = this.mini.getContext("2d")!;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, this.mini.width, this.mini.height);
    ctx.drawImage(this.miniBg, 0, 0);
    ctx.setTransform(d, 0, 0, d, 0, 0);
    const dur = a.track.duration;
    const va = (this.view.t0 / dur) * W, vb = (this.view.t1 / dur) * W;
    ctx.fillStyle = "rgba(0,0,0,0.6)";
    ctx.fillRect(0, 0, va, H); ctx.fillRect(vb, 0, W - vb, H);
    ctx.strokeStyle = "rgba(245,245,240,0.85)";
    ctx.lineWidth = 1;
    ctx.strokeRect(Math.round(va) + 0.5, 0.5, Math.max(3, vb - va - 1), H - 1);
    const px = (this.playT / dur) * W;
    ctx.fillStyle = "#F5F5F0";
    ctx.fillRect(Math.round(px), 0, 1.5, H);
  }

  // ---- interaction --------------------------------------------------------------------------
  private bind(): void {
    const el = this.over;
    const pointers = new Map<number, { x: number; y: number }>();
    let drag: { x: number; t0: number; moved: boolean } | null = null;
    let pinch: { dist: number; pps: number; cx: number } | null = null;
    const local = (e: PointerEvent | WheelEvent | MouseEvent) => {
      const r = el.getBoundingClientRect();
      return { x: e.clientX - r.left, y: e.clientY - r.top };
    };

    el.addEventListener("wheel", (e) => {
      if (!this.a) return;
      const { x } = local(e);
      if (e.ctrlKey || e.metaKey) {
        e.preventDefault();
        this.view.zoomAt(Math.exp(-e.deltaY * (e.deltaMode === 1 ? 0.05 : 0.0022)), Math.max(GUTTER, x));
        this.view.follow = false;
        this.onUserView();
      } else if (!e.shiftKey) {
        const dx = Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY;
        if (!dx) return;
        e.preventDefault();
        this.view.pan((dx * (e.deltaMode === 1 ? 16 : 1)) / this.view.pps);
        this.view.follow = false;
        this.onUserView();
      }
    }, { passive: false });

    el.addEventListener("pointerdown", (e) => {
      if (!this.a) return;
      const p = local(e);
      pointers.set(e.pointerId, p);
      el.setPointerCapture(e.pointerId);
      if (pointers.size === 2) {
        const [a, b] = [...pointers.values()];
        pinch = { dist: Math.hypot(a.x - b.x, a.y - b.y), pps: this.view.pps, cx: (a.x + b.x) / 2 };
        drag = null;
        return;
      }
      if (p.x < GUTTER) {
        const hit = this.placed.find((q) => p.y >= q.y && p.y < q.y + Math.min(q.h, 30) && q.lane !== ruler);
        if (hit) this.toggleLane(hit.lane.id);
        return;
      }
      drag = { x: p.x, t0: this.view.t0, moved: false };
    });
    el.addEventListener("pointermove", (e) => {
      if (!this.a) return;
      const p = local(e);
      if (pointers.has(e.pointerId)) pointers.set(e.pointerId, p);
      if (pinch && pointers.size === 2) {
        const [a, b] = [...pointers.values()];
        const dist = Math.hypot(a.x - b.x, a.y - b.y);
        const target = pinch.pps * (dist / Math.max(1, pinch.dist));
        this.view.zoomAt(target / this.view.pps, Math.max(GUTTER, pinch.cx));
        this.view.follow = false;
        return;
      }
      if (drag) {
        if (Math.abs(p.x - drag.x) > 4) drag.moved = true;
        if (drag.moved) {
          this.view.t0 = drag.t0 - (p.x - drag.x) / this.view.pps;
          this.view.clamp();
          this.view.follow = false;
          this.onUserView();
        }
      }
      this.setHover(p.x >= GUTTER ? this.view.t(p.x) : null);
      el.style.cursor = p.x < GUTTER ? (this.placed.some((q) => p.y >= q.y && p.y < q.y + Math.min(q.h, 30) && q.lane !== ruler) ? "pointer" : "default") : drag?.moved ? "grabbing" : "crosshair";
    });
    const end = (e: PointerEvent) => {
      pointers.delete(e.pointerId);
      if (pointers.size < 2) pinch = null;
      if (drag && !drag.moved && e.type === "pointerup") {
        const p = local(e);
        this.onSeek(Math.max(0, Math.min(this.view.duration, this.view.t(p.x))));
      }
      drag = null;
    };
    el.addEventListener("pointerup", end);
    el.addEventListener("pointercancel", end);
    el.addEventListener("pointerleave", () => this.setHover(null));

    // minimap
    let miniDrag = false;
    const miniSeek = (e: PointerEvent) => {
      const r = this.mini.getBoundingClientRect();
      const t = ((e.clientX - r.left) / r.width) * this.view.duration;
      this.view.showAt(t, 0.5);
      this.view.follow = false;
      this.onUserView();
    };
    this.mini.addEventListener("pointerdown", (e) => { if (!this.a) return; miniDrag = true; this.mini.setPointerCapture(e.pointerId); miniSeek(e); });
    this.mini.addEventListener("pointermove", (e) => { if (miniDrag) miniSeek(e); });
    this.mini.addEventListener("pointerup", () => { miniDrag = false; });
  }

  private setHover(t: number | null): void {
    if (t === this.hoverT) return;
    this.hoverT = t;
    this.onHover(t);
  }

  /** Lane label/time for tests and the inspector. */
  get lanesCanvas(): HTMLCanvasElement { return this.base; }
}
