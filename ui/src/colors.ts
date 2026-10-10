// Color system (spec §7). All color comes from the data.

export const INK = "#F5F5F0";
export const STEM: Record<string, string> = {
  drums: "#FF7A1A", bass: "#8B5CFF", vocals: "#7DF9FF", other: "#F5F5F0",
};
export const SECTION_PALETTE: Record<string, string> = {
  intro: "#5B6CFF", verse: "#2EC4B6", "pre-chorus": "#9BE564", prechorus: "#9BE564", chorus: "#FF3D7F",
  drop: "#FF2A2A", build: "#FFB627", bridge: "#B45CFF", break: "#00B8FF", inst: "#00B8FF",
  instrumental: "#00B8FF", solo: "#00B8FF", outro: "#7A7AA8", start: "#2A2A33", end: "#2A2A33", silence: "#2A2A33",
};
/** Disagreement / missing-vote marker. Distinct from the drop red so it never reads as a section. */
export const DISSENT = "#FF5A36";

export function sectionColor(s: { label: string; color?: string }): string {
  return s.color || SECTION_PALETTE[s.label?.toLowerCase()] || "#7A7AA8";
}

const FIFTHS = ["C", "G", "D", "A", "E", "B", "F#", "C#", "G#", "D#", "A#", "F"];
const ENHARMONIC: Record<string, string> = { Db: "C#", Eb: "D#", Gb: "F#", Ab: "G#", Bb: "A#", Cb: "B", Fb: "E", "E#": "F", "B#": "C" };
export function normRoot(r: string): string { return ENHARMONIC[r] ?? r; }
export function fifthsIndex(root: string): number { return FIFTHS.indexOf(normRoot(root)); }

const QUALITY_L: Record<string, number> = {
  maj: 68, maj7: 61, "7": 55, sus2: 62, sus4: 58, aug: 74, min: 42, min7: 36, dim: 28, hdim7: 30, dim7: 26,
};
const HSL_CACHE = new Map<string, [number, number, number]>();
/** Chord color: hue = root on circle of fifths, lightness = quality. Returns [h, s, l]. */
export function chordHSL(root: string, quality: string): [number, number, number] {
  const k = root + "|" + quality;
  let v = HSL_CACHE.get(k);
  if (!v) {
    const i = fifthsIndex(root);
    v = i < 0 || quality === "N" ? [0, 0, 22] : [(i * 30 + 15) % 360, 78, QUALITY_L[quality] ?? 52];
    HSL_CACHE.set(k, v);
  }
  return v;
}
export function chordColor(root: string, quality: string, alpha = 1): string {
  const [h, s, l] = chordHSL(root, quality);
  return `hsla(${h} ${s}% ${l}% / ${alpha})`;
}

export function hexToRgb(hex: string): [number, number, number] {
  let h = hex.replace("#", "");
  if (h.length === 3) h = h.split("").map((c) => c + c).join("");
  const n = parseInt(h.slice(0, 6), 16) || 0;
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
export function rgba(hex: string, a: number): string {
  const [r, g, b] = hexToRgb(hex);
  return `rgba(${r},${g},${b},${a})`;
}
export function hslToRgb01(h: number, s: number, l: number): [number, number, number] {
  s /= 100; l /= 100;
  const k = (n: number) => (n + h / 30) % 12;
  const a = s * Math.min(l, 1 - l);
  const f = (n: number) => l - a * Math.max(-1, Math.min(k(n) - 3, Math.min(9 - k(n), 1)));
  return [f(0), f(8), f(4)];
}
/** Black or white text, whichever reads on the given fill. */
export function inkOn(hex: string): string {
  const [r, g, b] = hexToRgb(hex);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b > 140 ? "#000" : INK;
}
