// AGREEMENT: one row per backend, showing its vote against the consensus.
//   beats:    a tick per consensus beat. Agreeing votes are quiet hairlines; missing votes are red
//             ticks that rise above the row, so dissent clusters jump out at any zoom.
//   sections: each backend's boundary support per consensus section (tick height = vote); zero vote = red gap.
//   key:      each backend's label, red when it disagrees with the consensus key.
import { DISSENT, sectionColor, rgba } from "../colors";
import type { Analysis } from "../types";
import { type Lane, type LaneCtx, MONO, DIM, text, fitLabel, visibleRange } from "./lane";

const ROW = 15;
const HEAD = 13;
const TOP = 12; // room for the lane name

export interface AgreeRow { kind: "beats" | "sections" | "key"; backend: string; nc: boolean; ok: boolean; error: string | null; agree: number; }

const cache = new WeakMap<Analysis, AgreeRow[]>();
export function agreementRows(a: Analysis): AgreeRow[] {
  const hit = cache.get(a);
  if (hit) return hit;
  const prov = (dim: string) => a.provenance.filter((p) => p.dimension === dim);
  const rows: AgreeRow[] = [];
  const add = (kind: AgreeRow["kind"], names: string[], dim: string) => {
    const p = prov(dim);
    const all = [...new Set([...p.map((x) => x.backend), ...names])];
    for (const b of all) {
      const pv = a.provenance.find((x) => x.backend === b && x.dimension === dim) ?? a.provenance.find((x) => x.backend === b);
      let agree = 0;
      if (kind === "beats") agree = a.beats.length ? a.beats.filter((x) => x.votes[b]).length / a.beats.length : 0;
      else if (kind === "sections") agree = a.sections.length ? a.sections.filter((x) => (x.votes[b] ?? 0) > 0).length / a.sections.length : 0;
      else agree = a.key.votes[b]?.label === a.key.label ? 1 : 0;
      rows.push({ kind, backend: b, nc: !!pv?.nc, ok: pv ? pv.ok : true, error: pv?.error ?? null, agree });
    }
  };
  const beatNames = new Set<string>(); for (const b of a.beats) for (const k in b.votes) beatNames.add(k);
  const secNames = new Set<string>(); for (const s of a.sections) for (const k in s.votes) secNames.add(k);
  add("beats", [...beatNames], "beats");
  add("sections", [...secNames], "sections");
  add("key", Object.keys(a.key.votes), "key");
  cache.set(a, rows);
  return rows;
}

function groups(a: Analysis) {
  const rows = agreementRows(a);
  const out: { kind: AgreeRow["kind"]; rows: AgreeRow[] }[] = [];
  for (const r of rows) {
    const g = out.at(-1);
    if (g && g.kind === r.kind) g.rows.push(r); else out.push({ kind: r.kind, rows: [r] });
  }
  return out;
}

export const agreementLane: Lane = {
  id: "agreement", name: "agreement", 
  height: (a) => groups(a).reduce((s, g) => s + HEAD + g.rows.length * ROW, 0) + 2 + TOP,
  note: (a) => `${agreementRows(a).length} backends`,
  draw(c) {
    let yy = c.y + TOP;
    for (const g of groups(c.a)) {
      c.ctx.fillStyle = "rgba(245,245,240,0.05)";
      c.ctx.fillRect(c.x0, yy + HEAD - 1, c.x1 - c.x0, 1);
      yy += HEAD;
      for (const r of g.rows) {
        drawRow(c, r, yy);
        yy += ROW;
      }
    }
  },
  gutter({ ctx, a, y }) {
    let yy = y + TOP;
    for (const g of groups(a)) {
      text(ctx, g.kind, 14, yy + HEAD / 2 + 1, `9px ${MONO}`, "rgba(245,245,240,0.3)");
      yy += HEAD;
      for (const r of g.rows) {
        const pct = `${Math.round(r.agree * 100)}%`;
        const col = !r.ok ? DISSENT : DIM;
        ctx.font = `9.5px ${MONO}`;
        const name = fitLabel(ctx, r.backend, r.nc ? 62 : 82);
        text(ctx, name, 20, yy + ROW / 2, `9.5px ${MONO}`, col);
        if (r.nc) {
          const w = ctx.measureText(name).width;
          text(ctx, "nc", 24 + w, yy + ROW / 2, `600 8.5px ${MONO}`, "#FFB627");
        }
        text(ctx, r.ok ? pct : "fail", 128, yy + ROW / 2, `9px ${MONO}`, r.ok && r.agree > 0.9 ? "rgba(245,245,240,0.3)" : DISSENT, "right");
        yy += ROW;
      }
    }
  },
};

function drawRow(c: LaneCtx, r: AgreeRow, y: number): void {
  const { ctx, a, view, x0, x1 } = c;
  const mid = y + ROW / 2;
  if (!r.ok) {
    ctx.save();
    ctx.beginPath(); ctx.rect(x0, y + 2, x1 - x0, ROW - 4); ctx.clip();
    ctx.strokeStyle = rgba(DISSENT, 0.35);
    for (let x = x0 - ROW; x < x1; x += 6) { ctx.beginPath(); ctx.moveTo(x, y + ROW); ctx.lineTo(x + ROW, y); ctx.stroke(); }
    ctx.restore();
    text(ctx, `failed: ${r.error ?? "no output"}`, x0 + 8, mid, `9.5px ${MONO}`, DISSENT);
    return;
  }
  if (r.kind === "beats") {
    // bucket per pixel column so dissent survives zooming out
    const [i0, i1] = visibleRange(a.beats, view.t0, view.t1, (b) => b.time);
    let lastX = -1, agreeN = 0, dissentN = 0;
    const flush = () => {
      if (lastX < 0) return;
      if (dissentN) {
        ctx.fillStyle = DISSENT;
        ctx.globalAlpha = Math.min(1, 0.55 + 0.45 * dissentN / (agreeN + dissentN));
        ctx.fillRect(lastX, y + 1, 1.5, ROW - 2);
      } else if (agreeN) {
        ctx.fillStyle = "rgba(245,245,240,0.42)";
        ctx.globalAlpha = 1;
        ctx.fillRect(lastX, mid - 2, 1, 4);
      }
      ctx.globalAlpha = 1;
    };
    for (let i = i0; i < i1; i++) {
      const b = a.beats[i];
      const x = Math.round(view.x(b.time));
      if (x > x1) break;
      if (x !== lastX) { flush(); lastX = x; agreeN = 0; dissentN = 0; }
      if (b.votes[r.backend]) agreeN++; else dissentN++;
    }
    flush();
  } else if (r.kind === "sections") {
    let vmax = 0;
    for (const s of a.sections) vmax = Math.max(vmax, s.votes[r.backend] ?? 0);
    const [i0, i1] = visibleRange(a.sections, view.t0, view.t1, (s) => s.start, (s) => s.end);
    for (let i = i0; i < i1; i++) {
      const s = a.sections[i];
      const v = s.votes[r.backend] ?? 0;
      const xa = Math.max(x0, view.x(s.start)), xb = Math.min(x1, view.x(s.end));
      const col = sectionColor(s);
      ctx.fillStyle = rgba(col, 0.16);
      ctx.fillRect(xa + 1, mid - 1, Math.max(0, xb - xa - 2), 2);
      const bx = Math.round(view.x(s.start));
      if (bx >= x0 && bx <= x1) {
        if (v <= 0) {
          ctx.fillStyle = DISSENT;
          ctx.fillRect(bx - 1, y + 1, 2, ROW - 2);
          ctx.fillRect(bx + 2, mid - 0.5, 6, 1);
        } else {
          const n = vmax > 0 ? v / vmax : 1;
          const hh = 3 + (ROW - 4) * n;
          ctx.fillStyle = col;
          ctx.globalAlpha = 0.35 + 0.65 * n;
          ctx.fillRect(bx, mid - hh / 2, 2, hh);
          ctx.globalAlpha = 1;
        }
        if (xb - xa > 46) text(ctx, v.toFixed(2), bx + 5, mid, `8.5px ${MONO}`, v <= 0 ? DISSENT : "rgba(245,245,240,0.38)");
      }
    }
  } else {
    const kv = a.key.votes[r.backend];
    const agree = kv?.label === a.key.label;
    ctx.fillStyle = agree ? "rgba(245,245,240,0.12)" : rgba(DISSENT, 0.5);
    ctx.fillRect(x0, mid - 0.5, x1 - x0, 1);
    const lab = kv ? `${kv.label}  ${kv.confidence.toFixed(2)}${agree ? "" : `   disagrees with consensus ${a.key.label}`}` : "no vote";
    ctx.fillStyle = "#000";
    ctx.font = `9.5px ${MONO}`;
    ctx.fillRect(x0 + 4, y + 1, ctx.measureText(lab).width + 8, ROW - 2);
    text(ctx, lab, x0 + 8, mid, `9.5px ${MONO}`, agree ? DIM : DISSENT);
  }
}
