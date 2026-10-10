"""Lyrics with word timing: faster-whisper (MIT) on the vocal stem. Extra: strata[lyrics]."""
from __future__ import annotations

from ._util import free_gpu
from .base import Backend, Context

MODEL = "large-v3-turbo"
MIN_VOCAL_SHARE = 0.05
MIN_LETTERS = 4
MIN_LOGPROB = -1.0


class WhisperLyrics(Backend):
    name = "lyrics_whisper"
    license = "MIT"
    optional = True
    weights = {"lyrics": 1.0}
    requires = ("vocals_activity",)

    def available(self) -> bool:
        try:
            import faster_whisper  # noqa: F401
            return True
        except Exception:
            return False

    def version(self) -> str:
        return f"{MODEL}-2"

    def run(self, ctx: Context) -> dict:
        act = ctx.results.get("vocals_activity", {}).get("activity", [])
        sung = sum(a["end"] - a["start"] for a in act)
        p = ctx.stems.get("vocals")
        if p is None or sung < MIN_VOCAL_SHARE * ctx.track["duration"]:
            return {"lyrics": [], "note": "no substantial vocals"}
        from faster_whisper import WhisperModel

        model = WhisperModel(MODEL, device="cuda" if ctx.device == "cuda" else "cpu",
                             compute_type="float16" if ctx.device == "cuda" else "int8")
        # Decode ourselves: faster-whisper's PyAV path breaks on recent PyAV releases.
        import librosa
        y, _ = librosa.load(str(p), sr=16000, mono=True)
        segs, info = model.transcribe(y, word_timestamps=True, vad_filter=True, condition_on_previous_text=False)
        lines = []
        for s in segs:
            text = s.text.strip()
            letters = sum(ch.isalpha() for ch in text)
            if letters < MIN_LETTERS or (s.no_speech_prob or 0) > 0.6 or (s.avg_logprob or 0) < MIN_LOGPROB:
                continue  # Whisper fills sparse or wordless vocals with short, low-confidence noise
            words = [{"start": round(w.start, 3), "end": round(w.end, 3), "word": w.word.strip()} for w in (s.words or [])]
            lines.append({"start": round(s.start, 3), "end": round(s.end, 3), "text": text, "words": words})
        del model
        free_gpu()
        return {"lyrics": lines, "language": info.language}


BACKEND = WhisperLyrics()
