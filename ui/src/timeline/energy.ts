// Loudness curve, filled with the section color underneath; builds as ramps, drops as markers.
import { sectionColor, rgba } from "../colors";
import { type Lane, MONO, curveMax, text, visibleRange } from "./lane";

const BUILD = "#FFB627";
const DROP = "#FF2A2A";

export const energyLane: Lane = {
  id: "energy", name: "energy", height: 64,
  note: (a) => `${a.dynamics.lufs.toFixed(1)} LUFS  ${a.dynamics.builds.length}b ${a.dynamics.drops.length}d`,
  draw({ ctx, a, view, y, h, x0, x1 }) {
    const d = a.curves.data.loudness ?? a.curves.data.rms;
    const top = y + 4, bot = y + h;
    const H = bot - top;
    const cols = Math.ceil(x1 - x0);
    const ys = new Float32Array(cols + 1);
    for (let c = 0; c <= cols; c++) ys[c] = bot - curveMax(d, a.curves.fps, view.t(x0 + c), view.t(x0 + c + 1)) * H;
    const path = new Path2D();
    path.moveTo(x0, bot);
    for (let c = 0; c <= cols; c++) path.lineTo(x0 + c, ys[c]);
    path.lineTo(x0 + cols, bot);
    path.closePath();
    // fill per section in its color, clipped to the curve
    ctx.save();
    ctx.clip(path);
    const [s0, s1] = visibleRange(a.sections, view.t0, view.t1, (s) => s.start, (s) => s.end);
    for (let i = s0; i < s1; i++) {
      const s = a.sections[i];
      const xa = Math.max(x0, view.x(s.start)), xb = Math.min(x1, view.x(s.end));
      const g = ctx.createLinearGradient(0, top, 0, bot);
      const col = sectionColor(s);
      g.addColorStop(0, rgba(col, 0.75));
      g.addColorStop(1, rgba(col, 0.08));
      ctx.fillStyle = g;
      ctx.fillRect(xa, top, xb - xa, H);
    }
    ctx.restore();
    ctx.beginPath();
    for (let c = 0; c <= cols; c++) c ? ctx.lineTo(x0 + c, ys[c]) : ctx.moveTo(x0, ys[0]);
    ctx.strokeStyle = "rgba(245,245,240,0.85)";
    ctx.lineWidth = 1;
    ctx.stroke();

    // builds: rising ramp, hatched
    for (const b of a.dynamics.builds) {
      const xa = view.x(b.start), xb = view.x(b.end);
      if (xb < x0 || xa > x1) continue;
      const peak = bot - H * (0.35 + 0.65 * b.strength);
      ctx.save();
      ctx.beginPath(); ctx.rect(x0, y, x1 - x0, h); ctx.clip();
      ctx.beginPath();
      ctx.moveTo(xa, bot); ctx.lineTo(xb, peak); ctx.lineTo(xb, bot); ctx.closePath();
      ctx.fillStyle = rgba(BUILD, 0.14); ctx.fill();
      ctx.save(); ctx.clip();
      ctx.strokeStyle = rgba(BUILD, 0.55); ctx.lineWidth = 1;
      for (let x = xa - H; x < xb; x += 5) { ctx.beginPath(); ctx.moveTo(x, bot); ctx.lineTo(x + H, top); ctx.stroke(); }
      ctx.restore();
      ctx.beginPath(); ctx.moveTo(xa, bot); ctx.lineTo(xb, peak); ctx.strokeStyle = BUILD; ctx.lineWidth = 1.5; ctx.stroke();
      if (xb - xa > 70) {
        ctx.fillStyle = "#000"; ctx.font = `9.5px ${MONO}`;
        const lab = `build ${b.strength.toFixed(2)}`;
        ctx.fillRect(xa + 4, bot - 15, ctx.measureText(lab).width + 8, 13);
        text(ctx, lab, xa + 8, bot - 8, `9.5px ${MONO}`, BUILD);
      }
      ctx.restore();
    }
    // drops: hard vertical + downward wedge sized by strength
    for (const dr of a.dynamics.drops) {
      const x = Math.round(view.x(dr.time)) + 0.5;
      if (x < x0 || x > x1) continue;
      const s = 4 + 6 * dr.strength;
      ctx.fillStyle = DROP;
      ctx.fillRect(x - 0.5, y, 2, h);
      ctx.beginPath(); ctx.moveTo(x - s, y); ctx.lineTo(x + s + 1, y); ctx.lineTo(x + 0.5, y + s * 1.3); ctx.closePath(); ctx.fill();
      ctx.font = `9.5px ${MONO}`;
      const lab = `drop ${dr.strength.toFixed(2)}`;
      ctx.fillStyle = "#000"; ctx.fillRect(x + s + 2, y, ctx.measureText(lab).width + 6, 13);
      text(ctx, lab, x + s + 5, y + 6.5, `9.5px ${MONO}`, DROP);
    }
  },
};
