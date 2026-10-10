"""basic-pitch (Spotify; Apache-2.0 code + weights) on the bass / vocals / other stems via ONNX."""
from __future__ import annotations

import logging
from contextlib import contextmanager

from .base import Backend, Context


@contextmanager
def _quiet():
    """basic-pitch logs a warning per missing runtime (tf/coreml/tflite) at import; we use ONNX."""
    root = logging.getLogger()
    level = root.level
    root.setLevel(logging.ERROR)
    try:
        yield
    finally:
        root.setLevel(level)

RANGES = {"bass": (28, 67), "vocals": (40, 88), "other": (28, 108)}  # MIDI pitch bounds per stem


class BasicPitch(Backend):
    name = "notes_basicpitch"
    license = "Apache-2.0"
    weights = {"notes": 1.0}
    requires = ("allin1", "demucs")

    def available(self) -> bool:
        try:
            with _quiet():
                import basic_pitch.inference  # noqa: F401
            import onnxruntime  # noqa: F401
            return True
        except Exception:
            return False

    def version(self) -> str:
        return "0.4-onnx"

    def run(self, ctx: Context) -> dict:
        from basic_pitch import ICASSP_2022_MODEL_PATH
        from basic_pitch.inference import Model, predict

        model = Model(ICASSP_2022_MODEL_PATH)
        out = {}
        for stem, (lo, hi) in RANGES.items():
            p = ctx.stems.get(stem)
            if p is None:
                out[stem] = []
                continue
            _, _, events = predict(str(p), model, minimum_note_length=80, onset_threshold=0.5, frame_threshold=0.3)
            notes = [{"start": round(float(s), 3), "end": round(float(e), 3), "pitch": int(n), "velocity": round(float(a), 3)}
                     for s, e, n, a, _ in events if lo <= n <= hi]
            out[stem] = sorted(notes, key=lambda x: (x["start"], x["pitch"]))
        return out


BACKEND = BasicPitch()
