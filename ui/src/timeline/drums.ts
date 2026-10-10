import { STEM } from "../colors";
import { type Lane, MONO, DIM, text, visibleRange } from "./lane";
import type { TimedStrength } from "../types";

const ROWS = [
  { k: "kick", color: STEM.drums },
  { k: "snare", color: "#FFC08A" },
  { k: "hat", color: "#FFE9D6" },
] as const;

export const drumsLane: Lane = {
  id: "drums", name: "drums", height: 60,
  note: (a) => `${a.events.kick.length}k ${a.events.snare.length}s ${a.events.hat.length}h`,
  draw({ ctx, a, view, y: y0, h: h0, x1 }) {
    const y = y0 + 14, h = h0 - 14;
    const rh = h / ROWS.length;
    ROWS.forEach((r, ri) => {
      const ev: TimedStrength[] = a.events[r.k];
      const base = y + (ri + 1) * rh - 1;
      ctx.fillStyle = "rgba(245,245,240,0.06)";
      ctx.fillRect(view.x(view.t0), base, x1 - view.x(view.t0), 1);
      const [i0, i1] = visibleRange(ev, view.t0, view.t1, (e) => e.time);
      const w = view.pps > 120 ? 2 : 1;
      ctx.fillStyle = r.color;
      for (let i = i0; i < i1; i++) {
        const e = ev[i];
        const x = Math.round(view.x(e.time));
        if (x > x1) break;
        const hh = Math.max(1.5, e.strength * (rh - 3));
        ctx.globalAlpha = 0.45 + 0.55 * e.strength;
        ctx.fillRect(x, base - hh, w, hh);
      }
      ctx.globalAlpha = 1;
    });
  },
  gutter({ ctx, a, y: y0, h: h0 }) {
    const y = y0 + 14, h = h0 - 14;
    const rh = h / ROWS.length;
    ROWS.forEach((r, i) => {
      ctx.fillStyle = r.color;
      ctx.fillRect(14, y + i * rh + rh / 2 - 3, 6, 6);
      text(ctx, `${r.k} ${a.events[r.k].length}`, 25, y + i * rh + rh / 2, `9.5px ${MONO}`, DIM);
    });
  },
};
