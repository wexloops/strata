// ORBS: the default visualizer. Every analysis layer gets one glowing orb (WebGL2, instanced sphere
// impostors, additive) plus a crisp Canvas2D overlay for labels, live values, arcs, ticks, the
// self-drawing waveform and Max-style bangs. Legibility first: point at an orb, read its layer.
//
// Composition (1920x1080 reference, scaled uniformly):
//   top-left time readout | top-center STRUCTURE | top-right DYNAMICS
//   left RHYTHM (beat + satellites + backend vote ticks, kick/snare/hat) and EVENTS (bangs)
//   center MIX ringed by STEMS, SPECTRUM arc below
//   right HARMONY (chord, key) and VOCALS (+ lyric)
//   bottom: waveform that draws itself up to the playhead, section boundaries marked
import type { Analysis, TimedStrength } from "./types";
import { type Moment, curveAt, lastAtOrBefore, fmtTime, spanAt } from "./query";
import { chordHSL, hexToRgb, hslToRgb01, sectionColor, STEM, DISSENT } from "./colors";
import { agreementRows } from "./timeline/agreement";
import { STEMS } from "./timeline/waveform";

const MONO = `"JetBrains Mono", ui-monospace, monospace`;
const DISPLAY = `"Big Shoulders Display", "JetBrains Mono", sans-serif`;
const INK = "#F5F5F0";
type RGB = [number, number, number];

const VS = `#version 300 es
layout(location=0) in vec2 corner;
layout(location=1) in vec4 a0;   // cx, cy, r, conf
layout(location=2) in vec4 a1;   // rgb, intensity
layout(location=3) in vec4 a2;   // kind, fill, turb, halo
uniform vec2 uRes;
out vec2 p; flat out vec4 v0; flat out vec4 v1; flat out vec4 v2;
const float HALO = 2.3;
void main(){
  p = corner*HALO; v0=a0; v1=a1; v2=a2;
  vec2 px = a0.xy + corner*HALO*a0.z;
  gl_Position = vec4(px/uRes*2.-1., 0., 1.); gl_Position.y = -gl_Position.y;
}`;

const FS = `#version 300 es
precision highp float;
in vec2 p; flat in vec4 v0; flat in vec4 v1; flat in vec4 v2;
uniform float uT; uniform vec3 uChord;
out vec4 o;
// 3D value noise: sampled on the reconstructed sphere surface, so there is no polar seam.
float h31(vec3 q){ q = fract(q*vec3(.1031,.1030,.0973)); q += dot(q, q.yxz + 33.33); return fract((q.x + q.y)*q.z); }
float vn3(vec3 x){
  vec3 i = floor(x), f = fract(x); f = f*f*(3. - 2.*f);
  return mix(mix(mix(h31(i), h31(i+vec3(1,0,0)), f.x), mix(h31(i+vec3(0,1,0)), h31(i+vec3(1,1,0)), f.x), f.y),
             mix(mix(h31(i+vec3(0,0,1)), h31(i+vec3(1,0,1)), f.x), mix(h31(i+vec3(0,1,1)), h31(i+vec3(1,1,1)), f.x), f.y), f.z);
}
mat2 rot(float a){ float c = cos(a), s = sin(a); return mat2(c, -s, s, c); }
void main(){
  float r = v0.z, conf = v0.w;
  vec3 base = v1.rgb; float I = v1.a;
  float kind = v2.x, fill = v2.y, turb = v2.z, haloK = v2.w;
  float d = length(p);
  // confidence → edge sharpness + opacity
  float soft = mix(.42, .03, conf) + 1.2/max(r,1.);
  float body = 1. - smoothstep(1. - soft, 1. + soft*.35, d);
  float z = sqrt(max(0., 1. - d*d));
  float fres = pow(1. - z, 2.4);
  float inner = exp(-d*d*2.4);
  vec3 col = base*(.10 + .55*inner*I) + mix(base, vec3(1.), .5)*fres*(.35 + .45*I) + vec3(1.)*pow(inner, 7.)*.30*I;
  if (kind > .5 && kind < 1.5) {           // MIX: chord swirl + flux/centroid turbulence
    vec3 nrm = vec3(p, sqrt(max(0., 1. - dot(p, p))));   // sphere surface normal
    // swirl = a rotation of the surface about the view axis that is stronger toward the rim (continuous everywhere)
    nrm.xy = rot(uT*.35 + (1. - nrm.z)*2.4) * nrm.xy;
    nrm.xz = rot(uT*.21) * nrm.xz;
    vec3 q = nrm*2.3 + vec3(0., 0., uT*.25);
    float n = vn3(q) * .65 + vn3(q*2.3 + 9.) * .35;
    n += turb * (vn3(q*5.5 + vec3(uT*1.7)) - .5) * 1.4;
    float band = smoothstep(.45, .85, n) * (1. - smoothstep(.55, .98, d));
    col += uChord * band * (.55 + .9*turb) * (.6 + .6*I);
    col += uChord * inner * .18;
  } else if (kind > 1.5 && kind < 2.5) {    // TENSION: fills bottom-up
    float lvl = 1. - 2.*fill;
    float wave = .04*sin(p.x*9. + uT*6.);
    float liquid = smoothstep(lvl + wave - .03, lvl + wave + .03, p.y);
    col = mix(col*.35, col + base*.9, liquid * step(.001, fill));
  }
  float alpha = mix(.4, 1., conf);
  float halo = exp(-max(d - 1., 0.)*3.2) * (1. - body) * haloK * (.25 + .5*I) * (.4 + .6*conf);
  vec3 outc = col*body*alpha + base*halo*.55;
  o = vec4(outc, 1.);
}`;

interface Orb { x: number; y: number; r: number; conf: number; c: RGB; I: number; kind?: number; fill?: number; turb?: number; halo?: number; }

const BANGS = ["beat", "downbeat", "bar", "section", "chord", "kick", "snare", "hat", "drop", "cue"] as const;
type Bang = typeof BANGS[number];

/** Per-analysis event lists for bangs and lookups, built once. */
interface Prepared {
  beats: number[]; downbeats: number[]; bars: number[]; sections: number[]; chords: number[]; cues: number[];
  backends: string[];
}
const prepCache = new WeakMap<Analysis, Prepared>();
function prep(a: Analysis): Prepared {
  let p = prepCache.get(a);
  if (p) return p;
  const chords: number[] = [];
  let last = "";
  for (const c of a.chords) { if (c.label !== last) chords.push(c.start); last = c.label; }
  p = {
    beats: a.beats.map((b) => b.time),
    downbeats: a.beats.filter((b) => b.downbeat).map((b) => b.time),
    bars: a.bars.map((b) => b.start),
    sections: a.sections.map((s) => s.start),
    chords,
    cues: a.cues.map((c) => c.time),
    backends: agreementRows(a).filter((r) => r.kind === "beats").map((r) => r.backend),
  };
  prepCache.set(a, p);
  return p;
}
const lastTime = (arr: number[], t: number) => { const i = lastAtOrBefore(arr, t, (x) => x); return i >= 0 ? { i, t: arr[i] } : null; };
const lastEv = (arr: TimedStrength[], t: number) => { const i = lastAtOrBefore(arr, t, (e) => e.time); return i >= 0 ? { i, e: arr[i] } : null; };
const rgb01 = (hex: string): RGB => hexToRgb(hex).map((v) => v / 255) as RGB;
const lerp3 = (a: RGB, b: RGB, k: number): RGB => [a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k, a[2] + (b[2] - a[2]) * k];
const smooth = (x: number) => { x = Math.max(0, Math.min(1, x)); return x * x * (3 - 2 * x); };
const css = (c: RGB, a = 1) => `rgba(${Math.round(c[0] * 255)},${Math.round(c[1] * 255)},${Math.round(c[2] * 255)},${a})`;

export class OrbsViz {
  readonly canvas: HTMLCanvasElement;
  readonly overlay: HTMLCanvasElement;
  gl: WebGL2RenderingContext | null = null;
  error: string | null = null;
  private prog: WebGLProgram | null = null;
  private inst: WebGLBuffer | null = null;
  private data = new Float32Array(12 * 96);
  private uRes: WebGLUniformLocation | null = null;
  private uT: WebGLUniformLocation | null = null;
  private uChord: WebGLUniformLocation | null = null;
  private chord: RGB = [0.5, 0.5, 0.55];
  private lastT = -1;
  private wave: { key: string; img: HTMLCanvasElement } | null = null;

  constructor(canvas: HTMLCanvasElement, overlay: HTMLCanvasElement) {
    this.canvas = canvas; this.overlay = overlay;
    const gl = canvas.getContext("webgl2", { antialias: true, alpha: false, preserveDrawingBuffer: true });
    if (!gl) { this.error = "This browser has no WebGL2, so the visualizer can't run."; return; }
    this.gl = gl;
    try {
      const sh = (type: number, src: string) => {
        const s = gl.createShader(type)!; gl.shaderSource(s, src); gl.compileShader(s);
        if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s) || "compile failed");
        return s;
      };
      const prog = gl.createProgram()!;
      gl.attachShader(prog, sh(gl.VERTEX_SHADER, VS)); gl.attachShader(prog, sh(gl.FRAGMENT_SHADER, FS));
      gl.linkProgram(prog);
      if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(prog) || "link failed");
      this.prog = prog;
      const vao = gl.createVertexArray(); gl.bindVertexArray(vao);
      const quad = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, quad);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
      gl.enableVertexAttribArray(0); gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
      this.inst = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, this.inst);
      gl.bufferData(gl.ARRAY_BUFFER, this.data.byteLength, gl.DYNAMIC_DRAW);
      for (let k = 0; k < 3; k++) {
        gl.enableVertexAttribArray(1 + k);
        gl.vertexAttribPointer(1 + k, 4, gl.FLOAT, false, 48, k * 16);
        gl.vertexAttribDivisor(1 + k, 1);
      }
      this.uRes = gl.getUniformLocation(prog, "uRes");
      this.uT = gl.getUniformLocation(prog, "uT");
      this.uChord = gl.getUniformLocation(prog, "uChord");
    } catch (e) {
      this.error = `The orbs shader failed to build: ${(e as Error).message}`;
      this.prog = null;
    }
  }

  private resize(): { W: number; H: number; d: number; dO: number } {
    const d = Math.min(1.5, window.devicePixelRatio || 1);
    const dO = Math.min(2, window.devicePixelRatio || 1);
    const W = this.canvas.clientWidth, H = this.canvas.clientHeight;
    const set = (c: HTMLCanvasElement, k: number) => {
      const w = Math.round(W * k), h = Math.round(H * k);
      if (c.width !== w || c.height !== h) { c.width = w; c.height = h; }
    };
    set(this.canvas, d); set(this.overlay, dO);
    return { W, H, d, dO };
  }

  frame(a: Analysis, m: Moment): void {
    const gl = this.gl;
    if (!gl || !this.prog) return;
    const { W, H, d, dO } = this.resize();
    const s = Math.min(W / 1920, H / 1080);
    const ox = (W - 1920 * s) / 2, oy = (H - 1080 * s) / 2;
    const X = (x: number) => ox + x * s, Y = (y: number) => oy + y * s;
    const t = m.t;
    const P = prep(a);
    const orbs: Orb[] = [];
    const ctx = this.overlay.getContext("2d")!;
    ctx.setTransform(dO, 0, 0, dO, 0, 0);
    ctx.clearRect(0, 0, W, H);

    // ---------- shared state ----------
    const secs = a.sections;
    const si = m.sectionIndex >= 0 ? m.sectionIndex : Math.max(0, lastAtOrBefore(secs, t, (x) => x.start));
    const sec = secs[si];
    const next = secs[si + 1];
    let secCol: RGB = sec ? rgb01(sectionColor(sec)) : [0.48, 0.48, 0.66];
    if (sec && next && t > next.start - 1.2) secCol = lerp3(secCol, rgb01(sectionColor(next)), smooth((t - (next.start - 1.2)) / 1.2));
    const chordTarget: RGB = m.chord && m.chord.root ? hslToRgb01(...chordHSL(m.chord.root, m.chord.quality)) : [0.42, 0.42, 0.46];
    const jump = Math.abs(t - this.lastT) > 0.25;
    this.chord = lerp3(this.chord, chordTarget, jump ? 1 : 0.12);
    this.lastT = t;
    const env = (arr: TimedStrength[], k: number) => { const l = lastEv(arr, t); return l && t - l.e.time < 1.5 ? { v: l.e.strength * Math.exp(-(t - l.e.time) * k), s: l.e.strength, n: l.i + 1 } : { v: 0, s: 0, n: l ? l.i + 1 : 0 }; };

    // ---------- helpers ----------
    const label = (x: number, y: number, name: string, value: string, col = "rgba(245,245,240,0.5)", align: CanvasTextAlign = "center") => {
      ctx.textAlign = align; ctx.textBaseline = "alphabetic";
      ctx.font = `${12 * s}px ${MONO}`; ctx.fillStyle = col; ctx.fillText(name, X(x), Y(y));
      ctx.font = `600 ${15 * s}px ${MONO}`; ctx.fillStyle = INK; ctx.fillText(value, X(x), Y(y + 18));
    };
    const group = (x: number, y: number, w: number, name: string) => {
      ctx.fillStyle = "rgba(245,245,240,0.16)";
      ctx.fillRect(X(x), Y(y), w * s, Math.max(1, 0.75 * s));
      ctx.font = `${11 * s}px ${MONO}`; ctx.fillStyle = "rgba(245,245,240,0.38)";
      ctx.textAlign = "left"; ctx.textBaseline = "bottom";
      ctx.fillText(name, X(x), Y(y - 5));
    };
    const orb = (o: Orb) => orbs.push({ ...o, x: X(o.x), y: Y(o.y), r: o.r * s });

    // ---------- time readout ----------
    ctx.textAlign = "left"; ctx.textBaseline = "alphabetic";
    ctx.font = `${12 * s}px ${MONO}`; ctx.fillStyle = "rgba(245,245,240,0.42)";
    ctx.fillText(a.track.title.slice(0, 60), X(64), Y(58));
    ctx.font = `800 ${78 * s}px ${DISPLAY}`; ctx.fillStyle = INK;
    ctx.fillText(fmtTime(t), X(60), Y(134));
    ctx.font = `600 ${17 * s}px ${MONO}`; ctx.fillStyle = INK;
    const bb = m.beat ? `bar ${m.beat.bar}.${m.beat.beat}` : "bar –";
    ctx.fillText(bb, X(64), Y(166));
    ctx.font = `${13 * s}px ${MONO}`; ctx.fillStyle = "rgba(245,245,240,0.5)";
    ctx.fillText(`${a.tempo.bpm.toFixed(1)} bpm   local ${m.bpm.toFixed(1)}   ${a.tempo.meter}/4   of ${fmtTime(a.track.duration, false)}`, X(200), Y(166));
    ctx.font = `${11 * s}px ${MONO}`; ctx.fillStyle = "rgba(245,245,240,0.32)";
    ["Each orb is one analysis layer, labeled with its live value.", "Soft, faint edges mean low model confidence.", "Ticks around the beat orb: each beat model's vote."]
      .forEach((line, i) => ctx.fillText(line, X(64), Y(206 + i * 16)));

    // ---------- STRUCTURE ----------
    group(780, 52, 360, "structure");
    if (sec) {
      const cx = 960, cy = 138, r = 44;
      orb({ x: cx, y: cy, r, conf: sec.confidence, c: secCol, I: 0.7, halo: 1 });
      // progress arc
      ctx.strokeStyle = css(secCol, 0.95); ctx.lineWidth = 2.5 * s; ctx.lineCap = "round";
      ctx.beginPath(); ctx.arc(X(cx), Y(cy), (r + 12) * s, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * m.sectionProgress); ctx.stroke();
      ctx.strokeStyle = "rgba(245,245,240,0.12)"; ctx.lineWidth = 1 * s;
      ctx.beginPath(); ctx.arc(X(cx), Y(cy), (r + 12) * s, 0, Math.PI * 2); ctx.stroke();
      ctx.textAlign = "center"; ctx.textBaseline = "alphabetic";
      ctx.font = `700 ${30 * s}px ${DISPLAY}`; ctx.fillStyle = css(secCol);
      ctx.fillText(`${sec.label}`, X(cx), Y(cy + r + 44));
      ctx.font = `${12 * s}px ${MONO}`; ctx.fillStyle = "rgba(245,245,240,0.55)";
      ctx.fillText(`section ${si + 1}/${secs.length}   ${Math.round(m.sectionProgress * 100)}%   conf ${sec.confidence.toFixed(2)}`, X(cx), Y(cy + r + 64));
      ctx.fillStyle = INK; ctx.font = `600 ${13 * s}px ${MONO}`;
      ctx.fillText(next ? `next ${next.label} in ${(next.start - t).toFixed(1)} s` : `ends in ${(a.track.duration - t).toFixed(1)} s`, X(cx), Y(cy + r + 83));
    }

    // ---------- DYNAMICS ----------
    group(1440, 52, 400, "dynamics");
    {
      const cx = 1530, cy = 138;
      const build = m.build ? m.build.strength * smooth((t - m.build.start) / Math.max(0.01, m.build.end - m.build.start)) : 0;
      const drop = lastEv(a.dynamics.drops, t);
      const dage = drop ? t - drop.e.time : 99;
      const burst = drop && dage < 3 ? drop.e.strength * Math.exp(-dage * 1.6) : 0;
      const tensionCol: RGB = burst > 0.05 ? lerp3([1, 0.71, 0.15], [1, 0.16, 0.16], Math.min(1, burst * 1.5)) : [1, 0.71, 0.15];
      orb({ x: cx, y: cy, r: 40 * (1 + 0.35 * burst), conf: 1, c: tensionCol, I: 0.35 + 1.6 * burst + 0.6 * build, kind: 2, fill: build, halo: 0.6 + 2 * burst });
      if (drop && dage < 1.2) {
        ctx.strokeStyle = `rgba(255,42,42,${(1 - dage / 1.2) * drop.e.strength})`; ctx.lineWidth = 2 * s;
        ctx.beginPath(); ctx.arc(X(cx), Y(cy), (46 + dage * 70) * s, 0, Math.PI * 2); ctx.stroke();
      }
      label(cx, cy + 78, "tension", build > 0.01 ? `build ${build.toFixed(2)}` : burst > 0.05 ? `drop ${drop!.e.strength.toFixed(2)}` : "steady",
        build > 0.01 ? "#FFB627" : burst > 0.05 ? "#FF5A36" : "rgba(245,245,240,0.5)");
      ctx.textAlign = "left"; ctx.textBaseline = "alphabetic";
      ctx.font = `800 ${46 * s}px ${DISPLAY}`; ctx.fillStyle = INK;
      ctx.fillText(a.dynamics.lufs ? a.dynamics.lufs.toFixed(1).replace("-", "−") : "–", X(1640), Y(140));
      ctx.font = `${12 * s}px ${MONO}`; ctx.fillStyle = "rgba(245,245,240,0.5)";
      ctx.fillText(`LUFS integrated   LRA ${a.dynamics.lra.toFixed(1)}`, X(1642), Y(162));
      ctx.fillText(`loudness now ${m.loudness.toFixed(2)}`, X(1642), Y(180));
    }

    // ---------- RHYTHM ----------
    group(150, 300, 360, "rhythm");
    {
      const cx = 330, cy = 450, r = 42;
      const meter = a.tempo.meter || 4;
      const bconf = m.beat?.confidence ?? 0.3;
      const flash = Math.pow(1 - m.beatPhase, 4);
      const isDown = !!m.beat?.downbeat;
      orb({ x: cx, y: cy, r: r * (1 + 0.12 * flash), conf: bconf, c: [0.96, 0.96, 0.94], I: 0.45 + (isDown ? 1.6 : 1.0) * flash, halo: 0.8 });
      // satellites = bar positions
      for (let k = 0; k < meter; k++) {
        const ang = -Math.PI / 2 + (k / meter) * Math.PI * 2;
        const lit = m.beat && m.beat.beat - 1 === k;
        const down = k === 0;
        orb({ x: cx + Math.cos(ang) * 78, y: cy + Math.sin(ang) * 78, r: down ? 11 : 8, conf: 1, c: down ? [1, 1, 1] : [0.8, 0.8, 0.8],
          I: lit ? (down ? 2.2 : 1.5) * (0.45 + 0.55 * flash) + 0.4 : 0.06, halo: lit ? 1.4 : 0.2 });
      }
      // beat phase dot
      const pa = -Math.PI / 2 + m.beatPhase * Math.PI * 2;
      ctx.strokeStyle = "rgba(245,245,240,0.10)"; ctx.lineWidth = 1 * s;
      ctx.beginPath(); ctx.arc(X(cx), Y(cy), 58 * s, 0, Math.PI * 2); ctx.stroke();
      orb({ x: cx + Math.cos(pa) * 58, y: cy + Math.sin(pa) * 58, r: 4.5, conf: 1, c: [1, 1, 1], I: 1.2, halo: 0.6 });
      // backend vote ticks (outer ring)
      const n = P.backends.length;
      ctx.textBaseline = "middle";
      P.backends.forEach((b, k) => {
        const ang = -Math.PI / 2 + Math.PI / 4 + (k / Math.max(1, n)) * Math.PI * 2;
        const voted = m.beat ? !!m.beat.votes[b] : false;
        const r0 = 98, r1 = 110;
        ctx.strokeStyle = voted ? INK : DISSENT; ctx.globalAlpha = voted ? 0.95 : 0.85;
        ctx.lineWidth = (voted ? 2.5 : 1.5) * s;
        ctx.beginPath(); ctx.moveTo(X(cx + Math.cos(ang) * r0), Y(cy + Math.sin(ang) * r0)); ctx.lineTo(X(cx + Math.cos(ang) * r1), Y(cy + Math.sin(ang) * r1)); ctx.stroke();
        ctx.globalAlpha = 1;
        ctx.font = `${10 * s}px ${MONO}`; ctx.fillStyle = voted ? "rgba(245,245,240,0.7)" : DISSENT;
        ctx.textAlign = Math.cos(ang) >= 0 ? "left" : "right";
        ctx.fillText(b.replace(/_beats$/, ""), X(cx + Math.cos(ang) * 118), Y(cy + Math.sin(ang) * 118));
      });
      ctx.strokeStyle = "rgba(245,245,240,0.10)"; ctx.lineWidth = 1 * s;
      ctx.beginPath(); ctx.arc(X(cx), Y(cy), 104 * s, 0, Math.PI * 2); ctx.stroke();
      const nv = m.beat ? Object.values(m.beat.votes).filter(Boolean).length : 0;
      label(cx, cy + 142, "beat", m.beat ? `${m.beat.beat}/${meter}  conf ${bconf.toFixed(2)}  ${nv}/${n} votes` : "–");

      const drums: [string, TimedStrength[], RGB, number][] = [
        ["kick", a.events.kick, rgb01(STEM.drums), 9], ["snare", a.events.snare, rgb01("#FFC08A"), 11], ["hat", a.events.hat, rgb01("#FFE9D6"), 16],
      ];
      drums.forEach(([name, ev, c, k], i) => {
        const e = env(ev, k);
        const x = 210 + i * 120, y = 668;
        orb({ x, y, r: 22 * (1 + 0.55 * e.v), conf: 1, c, I: 0.12 + 1.9 * e.v, halo: 0.4 + 1.6 * e.v });
        label(x, y + 52, name, e.n ? `${e.s.toFixed(2)}  #${e.n}` : "–");
      });
    }

    // ---------- EVENTS (bangs) ----------
    group(150, 770, 400, "events (bangs)");
    {
      const kickL = lastEv(a.events.kick, t), snL = lastEv(a.events.snare, t), hatL = lastEv(a.events.hat, t), dropL = lastEv(a.dynamics.drops, t);
      const at: Record<Bang, { t: number; n: number } | null> = {
        beat: wrap(lastTime(P.beats, t)), downbeat: wrap(lastTime(P.downbeats, t)), bar: wrap(lastTime(P.bars, t)),
        section: wrap(lastTime(P.sections, t)), chord: wrap(lastTime(P.chords, t)),
        kick: kickL ? { t: kickL.e.time, n: kickL.i + 1 } : null, snare: snL ? { t: snL.e.time, n: snL.i + 1 } : null,
        hat: hatL ? { t: hatL.e.time, n: hatL.i + 1 } : null, drop: dropL ? { t: dropL.e.time, n: dropL.i + 1 } : null,
        cue: wrap(lastTime(P.cues, t)),
      };
      const col: Record<Bang, string> = {
        beat: INK, downbeat: INK, bar: INK, section: css(secCol), chord: css(chordTarget), kick: STEM.drums, snare: "#FFC08A", hat: "#FFE9D6", drop: "#FF2A2A", cue: "#FFB627",
      };
      BANGS.forEach((b, i) => {
        const x = 150 + (i % 5) * 84, y = 800 + Math.floor(i / 5) * 78;
        const ev = at[b];
        const age = ev ? t - ev.t : 99;
        const f = age >= 0 && age < 0.25 ? 1 - age / 0.25 : 0;
        const sz = 30 * s;
        ctx.strokeStyle = "rgba(245,245,240,0.28)"; ctx.lineWidth = 1 * s;
        ctx.strokeRect(X(x), Y(y), sz, sz);
        const cx = X(x) + sz / 2, cy = Y(y) + sz / 2, rr = 10.5 * s;
        if (f > 0) {
          const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, rr * 2.4);
          g.addColorStop(0, col[b]); g.addColorStop(0.42, col[b]); g.addColorStop(1, "rgba(0,0,0,0)");
          ctx.globalAlpha = f; ctx.fillStyle = g;
          ctx.beginPath(); ctx.arc(cx, cy, rr * 2.4, 0, Math.PI * 2); ctx.fill();
          ctx.globalAlpha = 1;
        }
        ctx.strokeStyle = f > 0 ? col[b] : "rgba(245,245,240,0.5)"; ctx.lineWidth = 1.25 * s;
        ctx.beginPath(); ctx.arc(cx, cy, rr, 0, Math.PI * 2); ctx.stroke();
        ctx.textAlign = "left"; ctx.textBaseline = "alphabetic";
        ctx.font = `${11 * s}px ${MONO}`; ctx.fillStyle = f > 0 ? INK : "rgba(245,245,240,0.5)";
        ctx.fillText(b, X(x), Y(y + 46));
        ctx.font = `${10 * s}px ${MONO}`; ctx.fillStyle = "rgba(245,245,240,0.32)";
        ctx.fillText(ev ? `${ev.n}` : "–", X(x), Y(y + 60));
      });
    }

    // ---------- MIX + STEMS ----------
    const MX = 960, MY = 520;
    {
      const loud = m.loudness;
      const flux = curveAt(a, "flux", t), cen = curveAt(a, "centroid", t);
      const r = 62 + 92 * loud;
      orb({ x: MX, y: MY, r, conf: 1, c: secCol, I: 0.45 + 0.8 * loud, kind: 1, turb: Math.min(1, flux * 0.7 + cen * 0.4), halo: 0.9 });
      ctx.strokeStyle = "rgba(245,245,240,0.10)"; ctx.lineWidth = 1 * s;
      ctx.beginPath(); ctx.arc(X(MX), Y(MY), 154 * s, 0, Math.PI * 2); ctx.stroke();
      ctx.textAlign = "center"; ctx.textBaseline = "alphabetic";
      ctx.font = `${12 * s}px ${MONO}`; ctx.fillStyle = "rgba(245,245,240,0.6)";
      ctx.fillText("mix loudness", X(MX), Y(MY + 176));
      ctx.font = `600 ${18 * s}px ${MONO}`; ctx.fillStyle = INK;
      ctx.fillText(loud.toFixed(2), X(MX), Y(MY + 197));
      ctx.font = `${11 * s}px ${MONO}`; ctx.fillStyle = "rgba(245,245,240,0.5)";
      ctx.fillText(`swirl = chord   turbulence: flux ${flux.toFixed(2)}  centroid ${cen.toFixed(2)}`, X(MX), Y(MY + 215));

      const pos: Record<string, [number, number]> = { drums: [-1, -1], vocals: [1, -1], bass: [-1, 1], other: [1, 1] };
      STEMS.forEach((st) => {
        const v = curveAt(a, `rms_${st}`, t);
        const [dx, dy] = pos[st];
        const x = MX + dx * 285, y = MY + dy * 160;
        orb({ x, y, r: 14 + 44 * v, conf: 1, c: rgb01(STEM[st]), I: 0.25 + 1.1 * v, halo: 0.7 });
        // hairline spoke to the mix
        ctx.strokeStyle = "rgba(245,245,240,0.08)"; ctx.lineWidth = 1 * s;
        ctx.beginPath(); ctx.moveTo(X(MX + dx * 136), Y(MY + dy * 77)); ctx.lineTo(X(x - dx * 64), Y(y - dy * 36)); ctx.stroke();
        label(x + dx * 78, y + 4, `${st} stem`, v.toFixed(2), css(rgb01(STEM[st]), 0.85), dx > 0 ? "left" : "right");
      });
    }

    // ---------- SPECTRUM arc ----------
    {
      const CX = MX, CY = 190, R = 620, a0 = (111 * Math.PI) / 180, a1 = (69 * Math.PI) / 180;
      ctx.strokeStyle = "rgba(245,245,240,0.10)"; ctx.lineWidth = 1 * s;
      ctx.beginPath(); ctx.arc(X(CX), Y(CY), R * s, a1, a0); ctx.stroke();
      for (let b = 0; b < 8; b++) {
        const ang = a0 + (a1 - a0) * (b / 7);
        const v = curveAt(a, `band_${b}`, t);
        const x = CX + Math.cos(ang) * R, y = CY + Math.sin(ang) * R;
        const hue = 25 + (b / 7) * 200;
        orb({ x, y, r: 6 + 17 * v, conf: 1, c: hslToRgb01(hue, 70, 62), I: 0.2 + 1.2 * v, halo: 0.6 });
        ctx.textAlign = "center"; ctx.textBaseline = "alphabetic";
        ctx.font = `${10 * s}px ${MONO}`; ctx.fillStyle = "rgba(245,245,240,0.42)";
        ctx.fillText(`b${b}`, X(x + Math.cos(ang) * 34), Y(y + Math.sin(ang) * 34 + 4));
        ctx.font = `600 ${10.5 * s}px ${MONO}`; ctx.fillStyle = "rgba(245,245,240,0.8)";
        ctx.fillText(v.toFixed(2), X(x + Math.cos(ang) * 34), Y(y + Math.sin(ang) * 34 + 17));
      }
      ctx.font = `${11 * s}px ${MONO}`; ctx.fillStyle = "rgba(245,245,240,0.38)";
      ctx.textAlign = "right"; ctx.fillText("spectrum  low", X(CX + Math.cos(a0) * R - 36), Y(CY + Math.sin(a0) * R + 4));
      ctx.textAlign = "left"; ctx.fillText("high", X(CX + Math.cos(a1) * R + 36), Y(CY + Math.sin(a1) * R + 4));
    }

    // ---------- HARMONY ----------
    group(1440, 300, 400, "harmony");
    {
      const cx = 1560, cy = 430;
      const ch = m.chord;
      const cconf = ch ? ch.confidence : 0.3;
      const changed = ch ? t - ch.start : 9;
      const pop = Math.exp(-Math.max(0, changed) * 5);
      orb({ x: cx, y: cy, r: 46 * (1 + 0.12 * pop), conf: cconf, c: this.chord, I: 0.55 + 0.9 * pop, halo: 1 });
      ctx.textAlign = "left"; ctx.textBaseline = "alphabetic";
      ctx.font = `800 ${44 * s}px ${DISPLAY}`; ctx.fillStyle = css(chordTarget);
      ctx.fillText(ch && ch.root ? ch.label : "N.C.", X(cx + 72), Y(cy + 4));
      ctx.font = `${12 * s}px ${MONO}`; ctx.fillStyle = "rgba(245,245,240,0.55)";
      ctx.fillText(`chord   ${ch ? ch.label_full : "–"}   conf ${cconf.toFixed(2)}`, X(cx + 74), Y(cy + 26));

      const ky = 600;
      const local = m.key || a.key.label;
      const differs = !!local && local !== a.key.label;
      const kp = differs ? Math.pow(1 - m.beatPhase, 3) : 0;
      const tonicRoot = (local || a.key.label).split(" ")[0];
      const kmode = /minor/.test(local) ? "min" : "maj";
      const keyCol: RGB = tonicRoot ? hslToRgb01(...chordHSL(tonicRoot, kmode)) : [0.5, 0.5, 0.5];
      orb({ x: cx, y: ky, r: 36 * (1 + 0.15 * kp), conf: a.key.confidence || 0.5, c: keyCol, I: 0.45 + 1.2 * kp, halo: 0.7 + kp });
      if (differs) {
        ctx.strokeStyle = `rgba(255,182,39,${0.4 + 0.6 * kp})`; ctx.lineWidth = 1.5 * s;
        ctx.beginPath(); ctx.arc(X(cx), Y(ky), (48 + 8 * kp) * s, 0, Math.PI * 2); ctx.stroke();
      }
      ctx.textAlign = "left";
      ctx.font = `700 ${30 * s}px ${DISPLAY}`; ctx.fillStyle = INK;
      ctx.fillText(`${a.key.label}  ${a.key.camelot}`, X(cx + 62), Y(ky + 2));
      ctx.font = `${12 * s}px ${MONO}`; ctx.fillStyle = differs ? "#FFB627" : "rgba(245,245,240,0.55)";
      ctx.fillText(differs ? `key  local ${local} in this section` : `key   conf ${a.key.confidence.toFixed(2)}`, X(cx + 64), Y(ky + 24));
    }

    // ---------- VOCALS ----------
    group(1440, 715, 400, "vocals");
    {
      const cx = 1560, cy = 790;
      const act = spanAt(a.vocals.activity, t);
      let glow = act ? 1 : 0;
      if (!act) {
        const i = lastAtOrBefore(a.vocals.activity, t, (v) => v.start);
        if (i >= 0) glow = Math.max(0, 1 - (t - a.vocals.activity[i].end) * 3);
      }
      const rv = curveAt(a, "rms_vocals", t);
      orb({ x: cx, y: cy, r: 26 + 10 * rv, conf: 1, c: rgb01(STEM.vocals), I: 0.06 + 1.2 * glow * (0.5 + rv), halo: 0.2 + glow });
      ctx.textAlign = "left"; ctx.textBaseline = "alphabetic";
      ctx.font = `${12 * s}px ${MONO}`; ctx.fillStyle = "rgba(245,245,240,0.55)";
      ctx.fillText(`vocal activity   ${act ? "singing" : "none"}`, X(cx + 52), Y(cy - 4));
      ctx.font = `700 ${22 * s}px ${DISPLAY}`; ctx.fillStyle = m.lyric ? "#7DF9FF" : "rgba(245,245,240,0.25)";
      const lyr = m.lyric ? m.lyric.text : a.vocals.lyrics.length ? "between lines" : "no lyrics";
      ctx.fillText(lyr.length > 46 ? lyr.slice(0, 45) + "…" : lyr, X(cx + 52), Y(cy + 22));
    }

    // ---------- WAVEFORM (draws itself) ----------
    this.waveform(ctx, a, t, X(150), Y(968), 1620 * s, 70 * s, s, dO);

    // ---------- GL pass ----------
    this.chordU = this.chord;
    this.draw(orbs, W, H, d, t);
  }

  private chordU: RGB = [0.5, 0.5, 0.5];

  private waveform(ctx: CanvasRenderingContext2D, a: Analysis, t: number, x0: number, y0: number, w: number, h: number, s: number, dpr: number): void {
    const dur = a.track.duration;
    const key = `${a.track.id}|${Math.round(w)}|${Math.round(h)}|${dpr}`;
    if (!this.wave || this.wave.key !== key) {
      const img = document.createElement("canvas");
      img.width = Math.round(w * dpr); img.height = Math.round(h * dpr);
      const g = img.getContext("2d")!;
      g.scale(dpr, dpr);
      const cols = Math.round(w), mid = h / 2;
      const ds = STEMS.map((st) => a.curves.data[`rms_${st}`] ?? []);
      const fps = a.curves.fps;
      const stacks: Float32Array[] = STEMS.map(() => new Float32Array(cols));
      let mx = 1e-6;
      for (let c = 0; c < cols; c++) {
        const f0 = Math.floor((c / cols) * dur * fps), f1 = Math.max(f0 + 1, Math.floor(((c + 1) / cols) * dur * fps));
        let acc = 0;
        STEMS.forEach((_, k) => {
          let m = 0; const d = ds[k];
          for (let f = f0; f < f1 && f < d.length; f++) if (d[f] > m) m = d[f];
          acc += m; stacks[k][c] = acc;
        });
        if (acc > mx) mx = acc;
      }
      for (let k = STEMS.length - 1; k >= 0; k--) {
        g.fillStyle = STEM[STEMS[k]];
        g.globalAlpha = k === 3 ? 0.5 : 0.9;
        g.beginPath(); g.moveTo(0, mid);
        for (let c = 0; c < cols; c++) g.lineTo(c, mid - (stacks[k][c] / mx) * (mid - 1));
        for (let c = cols - 1; c >= 0; c--) g.lineTo(c, mid + (stacks[k][c] / mx) * (mid - 1));
        g.closePath(); g.fill();
      }
      this.wave = { key, img };
    }
    const px = (t / dur) * w;
    // baseline for the not-yet-heard part
    ctx.fillStyle = "rgba(245,245,240,0.12)";
    ctx.fillRect(x0 + px, y0 + h / 2, w - px, Math.max(1, 0.75 * s));
    if (px > 0) ctx.drawImage(this.wave.img, 0, 0, Math.round(px * dpr), this.wave.img.height, x0, y0, px, h);
    // section boundaries + labels
    ctx.textAlign = "left"; ctx.textBaseline = "alphabetic";
    for (const sc of a.sections) {
      const sx = x0 + (sc.start / dur) * w, ex = x0 + (sc.end / dur) * w;
      const c = sectionColor(sc);
      const heard = t >= sc.start;
      ctx.fillStyle = c; ctx.globalAlpha = heard ? 0.95 : 0.35;
      ctx.fillRect(sx + 1, y0 + h + 4 * s, Math.max(1, ex - sx - 2), 3 * s);
      ctx.fillRect(sx, y0 - 6 * s, Math.max(1, s), h + 13 * s);
      ctx.globalAlpha = 1;
      if (ex - sx > 40 * s) {
        ctx.font = `${10 * s}px ${MONO}`; ctx.fillStyle = heard ? "rgba(245,245,240,0.75)" : "rgba(245,245,240,0.3)";
        ctx.fillText(sc.label, sx + 4 * s, y0 - 8 * s);
      }
    }
    for (const dr of a.dynamics.drops) {
      const dx = x0 + (dr.time / dur) * w;
      ctx.fillStyle = "#FF2A2A"; ctx.globalAlpha = t >= dr.time ? 1 : 0.4;
      ctx.beginPath(); ctx.moveTo(dx - 5 * s, y0 + h + 10 * s); ctx.lineTo(dx + 5 * s, y0 + h + 10 * s); ctx.lineTo(dx, y0 + h + 3 * s); ctx.fill();
      ctx.globalAlpha = 1;
    }
    // playhead
    ctx.fillStyle = INK;
    ctx.fillRect(x0 + px - 0.75, y0 - 4 * s, 1.5, h + 8 * s);
    ctx.font = `${11 * s}px ${MONO}`; ctx.fillStyle = "rgba(245,245,240,0.5)";
    ctx.textAlign = "right"; ctx.fillText(fmtTime(a.track.duration, false), x0 + w, y0 + h + 24 * s);
    ctx.textAlign = "left"; ctx.fillText("waveform  drums bass vocals other", x0, y0 + h + 24 * s);
  }

  private draw(orbs: Orb[], W: number, H: number, d: number, t: number): void {
    const gl = this.gl!;
    const n = Math.min(orbs.length, this.data.length / 12);
    for (let i = 0; i < n; i++) {
      const o = orbs[i], j = i * 12;
      this.data.set([o.x * d, o.y * d, o.r * d, o.conf, o.c[0], o.c[1], o.c[2], o.I, o.kind ?? 0, o.fill ?? 0, o.turb ?? 0, o.halo ?? 1], j);
    }
    gl.viewport(0, 0, this.canvas.width, this.canvas.height);
    gl.clearColor(0, 0, 0, 1); gl.clear(gl.COLOR_BUFFER_BIT);
    gl.useProgram(this.prog);
    gl.enable(gl.BLEND); gl.blendFunc(gl.ONE, gl.ONE);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.inst);
    gl.bufferSubData(gl.ARRAY_BUFFER, 0, this.data, 0, n * 12);
    gl.uniform2f(this.uRes, this.canvas.width, this.canvas.height);
    gl.uniform1f(this.uT, t);
    gl.uniform3fv(this.uChord, this.chordU);
    gl.drawArraysInstanced(gl.TRIANGLE_STRIP, 0, 4, n);
    void W; void H;
  }
}

function wrap(x: { i: number; t: number } | null): { t: number; n: number } | null { return x ? { t: x.t, n: x.i + 1 } : null; }
