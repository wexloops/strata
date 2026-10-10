// Ranked edit cues (spec §5): lollipops, height + size = strength.
import { sectionColor } from "../colors";
import { spanAt } from "../query";
import { type Lane, visibleRange } from "./lane";

export const CUE_COLORS: Record<string, string> = { drop: "#FF2A2A", downbeat: "rgba(245,245,240,0.55)", accent: "#FF7A1A" };

export const cuesLane: Lane = {
  id: "cues", name: "cues", height: 40,
  note: (a) => `${a.cues.length} ranked`,
  draw({ ctx, a, view, y, h, x1 }) {
    const [i0, i1] = visibleRange(a.cues, view.t0, view.t1, (c) => c.time);
    const order = a.cues.slice(i0, i1).sort((p, q) => p.strength - q.strength); // strongest on top
    for (const c of order) {
      const x = Math.round(view.x(c.time)) + 0.5;
      if (x > x1) continue;
      const col = c.type === "section" ? sectionColor(spanAt(a.sections, c.time + 0.01) ?? { label: c.label }) : CUE_COLORS[c.type] ?? "#F5F5F0";
      const stemH = 6 + (h - 12) * c.strength;
      const r = 1.5 + 3.5 * c.strength;
      ctx.fillStyle = col;
      ctx.fillRect(x - 0.5, y + h - stemH, 1, stemH);
      ctx.beginPath(); ctx.arc(x, y + h - stemH, r, 0, Math.PI * 2);
      if (c.type === "downbeat") { ctx.strokeStyle = col; ctx.lineWidth = 1; ctx.stroke(); } else ctx.fill();
    }
  },
};
