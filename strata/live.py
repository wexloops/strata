"""Live OSC clock: plays an analysis as OSC in sync with a transport (spec §9)."""
from __future__ import annotations

import bisect
import threading
import time
from typing import Callable

Msg = tuple[str, list]
EDGE_EVENTS = ("kick", "snare", "hat")
SEEK_JUMP = 1.0  # a forward step larger than this is treated as a seek (no edge burst)


class Clock:
    def __init__(self):
        self._lock = threading.Lock()
        self._t0 = 0.0
        self._wall = 0.0
        self.playing = False

    def play(self, at: float | None = None) -> None:
        with self._lock:
            if at is not None:
                self._t0 = at
            elif self.playing:
                return
            self._wall = time.perf_counter()
            self.playing = True

    def pause(self) -> None:
        with self._lock:
            if self.playing:
                self._t0 += time.perf_counter() - self._wall
                self.playing = False

    def seek(self, t: float) -> None:
        with self._lock:
            self._t0 = max(0.0, t)
            self._wall = time.perf_counter()

    def time(self) -> float:
        with self._lock:
            return self._t0 + (time.perf_counter() - self._wall if self.playing else 0.0)


def _times(items: list[dict], key: str = "time") -> list[float]:
    return [x[key] for x in items]


class OscEmitter:
    """Pure message generator: tick(t_prev, t_now) -> messages. Sending is the caller's job."""

    def __init__(self, a: dict):
        self.a = a
        self.beats = a["beats"]
        self.bt = _times(self.beats)
        self.secs = a["sections"]
        self.st = _times(self.secs, "start")
        self.chords = a["chords"]
        self.ct = _times(self.chords, "start")
        self.bars = a["bars"]
        self.bar_t = _times(self.bars, "start")
        self.events = {k: a["events"][k] for k in EDGE_EVENTS}
        self.drops = a["dynamics"]["drops"]
        self.cues = a["cues"]
        self.curves = a["curves"]
        self.duration = a["track"]["duration"]

    @staticmethod
    def _crossed(times: list[float], t0: float, t1: float) -> range:
        return range(bisect.bisect_right(times, t0), bisect.bisect_right(times, t1))

    def _phase(self, times: list[float], t: float) -> float:
        i = bisect.bisect_right(times, t) - 1
        if i < 0 or i + 1 >= len(times):
            return 0.0
        return (t - times[i]) / max(times[i + 1] - times[i], 1e-6)

    def state(self, t: float) -> list[Msg]:
        """Full current state (sent after a seek so receivers resync)."""
        out: list[Msg] = []
        i = bisect.bisect_right(self.st, t) - 1
        if i >= 0:
            out.append(("/strata/section", [self.secs[i]["label"], self.secs[i]["index"]]))
        j = bisect.bisect_right(self.ct, t) - 1
        if j >= 0:
            out.append(("/strata/chord", [self.chords[j]["label"]]))
        return out

    def continuous(self, t: float) -> list[Msg]:
        out: list[Msg] = [("/strata/time", [round(t, 4)]),
                          ("/strata/beat/phase", [round(self._phase(self.bt, t), 4)]),
                          ("/strata/bar/phase", [round(self._phase(self.bar_t, t), 4)])]
        i = bisect.bisect_right(self.st, t) - 1
        if i >= 0:
            s = self.secs[i]
            out.append(("/strata/section/progress", [round((t - s["start"]) / max(s["end"] - s["start"], 1e-6), 4)]))
        fr = int(t * self.curves["fps"])
        for name, arr in self.curves["data"].items():
            if arr:
                out.append((f"/strata/curve/{name}", [float(arr[min(max(fr, 0), len(arr) - 1)])]))
        return out

    def edges(self, t0: float, t1: float) -> list[Msg]:
        out: list[Msg] = []
        for i in self._crossed(self.bt, t0, t1):
            b = self.beats[i]
            out.append(("/strata/beat", [i, b["beat"]]))
            if b["downbeat"]:
                out.append(("/strata/downbeat", [b["bar"]]))
                out.append(("/strata/bar", [b["bar"]]))
        for i in self._crossed(self.st, t0, t1):
            out.append(("/strata/section", [self.secs[i]["label"], self.secs[i]["index"]]))
        for i in self._crossed(self.ct, t0, t1):
            out.append(("/strata/chord", [self.chords[i]["label"]]))
        for k, evs in self.events.items():
            for i in self._crossed(_times(evs), t0, t1):
                out.append((f"/strata/{k}", [evs[i]["strength"]]))
        for i in self._crossed(_times(self.drops), t0, t1):
            out.append(("/strata/drop", [self.drops[i]["strength"]]))
        for i in self._crossed(_times(self.cues), t0, t1):
            out.append(("/strata/cue", [self.cues[i]["type"], self.cues[i]["strength"]]))
        return out

    def tick(self, t_prev: float, t_now: float) -> list[Msg]:
        msgs = self.continuous(t_now)
        if t_now < t_prev or t_now - t_prev > SEEK_JUMP:
            return msgs + self.state(t_now)
        return msgs + self.edges(t_prev, t_now)


class LiveSession:
    """Sends OSC for an analysis at `fps`, following a Clock. Optional OSC control input."""

    def __init__(self, a: dict, host: str, port: int, fps: int = 60, listen: int | None = None,
                 on_send: Callable[[list[Msg]], None] | None = None):
        from pythonosc.udp_client import SimpleUDPClient

        self.emitter = OscEmitter(a)
        self.client = SimpleUDPClient(host, port)
        self.clock = Clock()
        self.fps = fps
        self.listen = listen
        self.on_send = on_send
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._server = None

    def _loop(self) -> None:
        prev = self.clock.time()
        period = 1.0 / self.fps
        nxt = time.perf_counter()
        while not self._stop.is_set():
            t = self.clock.time()
            if self.clock.playing or t != prev:
                msgs = self.emitter.tick(prev, t)
                for addr, args in msgs:
                    self.client.send_message(addr, args)
                if self.on_send:
                    self.on_send(msgs)
                prev = t
            nxt += period
            time.sleep(max(0.0, nxt - time.perf_counter()))

    def _serve_control(self) -> None:
        from pythonosc.dispatcher import Dispatcher
        from pythonosc.osc_server import ThreadingOSCUDPServer

        d = Dispatcher()
        d.map("/strata/play", lambda *_: self.clock.play())
        d.map("/strata/pause", lambda *_: self.clock.pause())
        d.map("/strata/seek", lambda _addr, t=0.0, *__: self.clock.seek(float(t)))
        self._server = ThreadingOSCUDPServer(("0.0.0.0", self.listen), d)
        self._server.serve_forever()

    def start(self) -> "LiveSession":
        self._threads.append(threading.Thread(target=self._loop, daemon=True))
        if self.listen:
            self._threads.append(threading.Thread(target=self._serve_control, daemon=True))
        for th in self._threads:
            th.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        if self._server:
            self._server.shutdown()
