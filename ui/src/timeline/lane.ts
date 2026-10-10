// Lane contract. Each lane draws its own band of the base canvas.
import type { Analysis } from "../types";
import type { View } from "./view";

export const MONO = `"JetBrains Mono", ui-monospace, monospace`;
export const DISPLAY = `"Big Shoulders Display", "JetBrains Mono", sans-serif`;
export const HAIR = "rgba(245,245,240,0.10)";
export const DIM = "rgba(245,245,240,0.42)";

export interface LaneCtx {
  ctx: CanvasRenderingContext2D;
  a: Analysis;
  view: View;
  y: number; // top of lane content
  h: number; // content height
  x0: number; // left of plot area
  x1: number; // right of plot area
}

export interface Lane {
  id: string;
  name: string;
  height: number | ((a: Analysis) => number);
  /** Short data note under the name in the gutter. */
  note?: (a: Analysis) => string;
  /** Extra gutter rows (e.g. agreement backend names); y relative to lane top. */
  gutter?: (c: LaneCtx) => void;
  draw: (c: LaneCtx) => void;
}

export function laneHeight(l: Lane, a: Analysis): number {
  return typeof l.height === "function" ? l.height(a) : l.height;
}

/** Visible index range [i0, i1) of a time-sorted array. */
export function visibleRange<T>(arr: T[], t0: number, t1: number, start: (x: T) => number, end: (x: T) => number = start): [number, number] {
  let lo = 0, hi = arr.length;
  while (lo < hi) { const m = (lo + hi) >> 1; if (end(arr[m]) < t0) lo = m + 1; else hi = m; }
  let i1 = lo;
  while (i1 < arr.length && start(arr[i1]) <= t1) i1++;
  return [lo, i1];
}

export function text(ctx: CanvasRenderingContext2D, s: string, x: number, y: number, font: string, color: string, align: CanvasTextAlign = "left", base: CanvasTextBaseline = "middle"): void {
  ctx.font = font; ctx.fillStyle = color; ctx.textAlign = align; ctx.textBaseline = base;
  ctx.fillText(s, x, y);
}

/** Fit a label into width w; returns "" when nothing useful fits. */
export function fitLabel(ctx: CanvasRenderingContext2D, s: string, w: number): string {
  if (ctx.measureText(s).width <= w) return s;
  let lo = 0, hi = s.length;
  while (lo < hi) { const m = (lo + hi + 1) >> 1; if (ctx.measureText(s.slice(0, m) + "…").width <= w) lo = m; else hi = m - 1; }
  return lo >= 2 ? s.slice(0, lo) + "…" : "";
}

/** Max of a curve over frames covering [ta, tb). */
export function curveMax(d: number[] | undefined, fps: number, ta: number, tb: number): number {
  if (!d || !d.length) return 0;
  const f0 = Math.max(0, Math.floor(ta * fps));
  const f1 = Math.min(d.length - 1, Math.max(f0, Math.ceil(tb * fps) - 1));
  if (f1 - f0 <= 1) {
    const f = ta * fps, i = Math.max(0, Math.min(d.length - 1, Math.floor(f))), j = Math.min(d.length - 1, i + 1), u = f - Math.floor(f);
    return d[i] * (1 - u) + d[j] * u;
  }
  let m = 0;
  for (let i = f0; i <= f1; i++) if (d[i] > m) m = d[i];
  return m;
}
