// Hover inspector: every layer at one instant.
import type { Analysis } from "./types";
import { type Moment, momentAt, fmtTime, curveAt } from "./query";
import { chordColor, sectionColor, STEM, DISSENT } from "./colors";
import { midiName } from "./timeline/notes";
import { STEMS } from "./timeline/waveform";
import { lastAtOrBefore } from "./query";

const esc = (s: string) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);
const ms = (d: number) => `${d >= 0 ? "+" : "−"}${Math.abs(d) >= 10 ? `${Math.abs(d).toFixed(1)} s` : `${Math.abs(Math.round(d * 1000))} ms`}`;

export class Inspector {
  private el: HTMLElement;
  private lastKey = "";

  /** Forget the cached readout (call when a different analysis is loaded). */
  reset(): void {
    this.lastKey = "";
  }
  constructor(el: HTMLElement) { this.el = el; el.classList.add("insp"); }

  render(a: Analysis, t: number, source: "hover" | "playhead"): void {
    const key = `${source}|${t.toFixed(3)}`;
    if (key === this.lastKey) return;
    this.lastKey = key;
    const m = momentAt(a, t);
    this.el.innerHTML = this.html(a, m, source);
  }

  private html(a: Analysis, m: Moment, source: string): string {
    const s = m.section;
    const sc = s ? sectionColor(s) : "#2A2A33";
    const bb = m.beat ? `${m.beat.bar}.${m.beat.beat}` : "–";
    const row = (k: string, v: string, extra = "") => `<div class="ir"><span class="ik">${k}</span><span class="iv"${extra}>${v}</span></div>`;
    const ev = (name: string, e: { time: number; strength: number } | null, col: string) =>
      e ? `<div class="ir"><span class="ik"><i class="sw" style="background:${col}"></i>${name}</span><span class="iv">${ms(e.time - m.t)}<b class="meter"><b style="width:${(e.strength * 100).toFixed(0)}%;background:${col}"></b></b></span></div>` : "";
    const stems = STEMS.map((st) => {
      const v = curveAt(a, `rms_${st}`, m.t);
      return `<div class="bar-v" title="${st} ${v.toFixed(2)}"><b style="height:${(v * 100).toFixed(0)}%;background:${STEM[st]}"></b></div>`;
    }).join("");
    const bands = Array.from({ length: 8 }, (_, i) => {
      const v = curveAt(a, `band_${i}`, m.t);
      return `<div class="bar-v" title="band ${i} ${v.toFixed(2)}"><b style="height:${(v * 100).toFixed(0)}%"></b></div>`;
    }).join("");
    const notes = (["bass", "vocals", "other"] as const).map((k) => {
      const arr = a.notes[k];
      const i = lastAtOrBefore(arr, m.t, (n) => n.start);
      let held: number[] = [];
      for (let j = i; j >= 0 && j > i - 12; j--) if (arr[j].end > m.t) held.push(arr[j].pitch);
      held = [...new Set(held)].sort((x, y) => x - y);
      return held.length ? `<span style="color:${STEM[k]}">${held.map(midiName).join(" ")}</span>` : "";
    }).filter(Boolean).join("  ");
    const votes = m.beat ? Object.entries(m.beat.votes).map(([b, v]) => `<span class="${v ? "" : "dissent"}">${esc(b)}</span>`).join(" ") : "";
    return `
      <div class="i-head">
        <div class="i-src">${source === "hover" ? "cursor" : "playhead"}</div>
        <div class="i-time">${fmtTime(m.t)}</div>
        <div class="i-bb"><span>bar.beat</span> ${bb}</div>
      </div>
      <div class="i-sec" style="--c:${sc}">
        <div class="i-sec-l">${s ? esc(s.label) : "no section"}</div>
        <div class="i-sec-m">${s ? `part ${s.index + 1} of ${a.sections.length}  ${Math.round(m.sectionProgress * 100)}%` : ""}</div>
        <div class="i-prog"><b style="width:${(m.sectionProgress * 100).toFixed(1)}%"></b></div>
      </div>
      <div class="i-grid">
        ${row("chord", m.chord ? `<i class="sw" style="background:${chordColor(m.chord.root, m.chord.quality)}"></i>${esc(m.chord.label)} <em>${esc(m.chord.label_full)}  ${m.chord.confidence.toFixed(2)}</em>` : "–")}
        ${row("key", `${esc(m.key)}${m.key === a.key.label && a.key.camelot ? ` <em>${esc(a.key.camelot)}</em>` : ""}`)}
        ${row("tempo", `${m.bpm.toFixed(1)} <em>bpm local</em>`)}
        ${row("energy", `${m.loudness.toFixed(2)}<b class="meter"><b style="width:${(m.loudness * 100).toFixed(0)}%"></b></b>`)}
        ${s ? row("section energy", `${s.energy.toFixed(2)} <em>conf ${s.confidence.toFixed(2)}</em>`) : ""}
        ${m.build ? row("build", `<span style="color:#FFB627">rising ${m.build.strength.toFixed(2)}</span>`) : ""}
        ${m.beat ? row("beat conf", `${m.beat.confidence.toFixed(2)}`, m.beat.confidence < 0.75 ? ` style="color:${DISSENT}"` : "") : ""}
        ${votes ? `<div class="ir votes"><span class="ik">beat votes</span><span class="iv">${votes}</span></div>` : ""}
      </div>
      <div class="i-sub">nearest events</div>
      <div class="i-grid">
        ${ev("kick", m.kick, STEM.drums)}${ev("snare", m.snare, "#FFC08A")}${ev("hat", m.hat, "#FFE9D6")}
        ${m.drop ? ev("drop", m.drop, "#FF2A2A") : ""}
        ${m.cue ? row(`last cue`, `${esc(m.cue.label || m.cue.type)} <em>${m.cue.strength.toFixed(2)}</em> ${ms(m.cue.time - m.t)}`) : ""}
      </div>
      <div class="i-sub">notes held</div>
      <div class="i-notes">${notes || "<em>none</em>"}</div>
      <div class="i-sub">lyrics</div>
      <div class="i-lyric">${m.lyric ? esc(m.lyric.text) : "<em>no lyric at this moment</em>"}</div>
      <div class="i-bars">
        <div><div class="bars">${stems}</div><div class="i-cap">stems</div></div>
        <div><div class="bars bands">${bands}</div><div class="i-cap">bands 0–7</div></div>
      </div>
      ${s && s.tags?.length ? `<div class="i-tags">${s.tags.map((x) => `<span>${esc(x)}</span>`).join("")}</div>` : ""}`;
  }
}
