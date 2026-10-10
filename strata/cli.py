"""`strata` command line."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from . import __version__

DEFAULT_PORT = 3090


def _progress(e: dict) -> None:
    if "stage" in e:
        print(f"  [{e['progress'] * 100:5.1f}%] {e['message'] or e['stage']}", file=sys.stderr, flush=True)


def cmd_analyze(args) -> int:
    from .backends.base import registry
    from .exporters import export
    from .library import Library
    from .pipeline import analyze
    from .query import summary

    lib = Library()
    backends = registry(args.profile, include_optional=not args.fast)
    code = 0
    for p in args.paths:
        path = Path(p)
        if not path.exists():
            print(f"strata: no such file: {p}", file=sys.stderr)
            code = 2
            continue
        print(f"analyzing {path.name}", file=sys.stderr)
        a = analyze(path, profile=args.profile, fps=args.fps, device=args.device, progress=_progress,
                    only=backends, lib=lib, force=args.force)
        print(summary(a))
        if args.export:
            out = Path(args.out) if args.out else lib.exports_dir(a["track"]["id"])
            files = export(a, args.export.split(","), out, path)
            print(f"exported {len(files)} files -> {out}")
        print(f"analysis: {lib.analysis_path(a['track']['id'])}")
    return code


def _resolve(target: str) -> dict:
    from .query import resolve
    return resolve(target)


def cmd_export(args) -> int:
    from .exporters import export
    from .library import Library

    a = _resolve(args.target)
    out = Path(args.out) if args.out else Library().exports_dir(a["track"]["id"])
    audio = Path(a["track"]["path"])
    files = export(a, args.format.split(","), out, audio if audio.exists() else None)
    for f in files:
        print(f)
    return 0


def cmd_query(args) -> int:
    from . import query

    a = _resolve(args.target)
    if args.at is not None:
        res = query.at(a, args.at)
    elif args.sections:
        res = query.sections(a)
    elif args.cues:
        res = query.cues(a, args.min, args.type.split(",") if args.type else None)
    elif args.beats:
        res = query.beats(a, args.start, args.end, args.downbeats)
    else:
        print(query.summary(a))
        return 0
    if args.json or not isinstance(res, list):
        print(json.dumps(res, indent=1, ensure_ascii=False))
    else:
        for r in res:
            t = r.get("time", r.get("start"))
            rest = {k: v for k, v in r.items() if k not in ("time", "start", "votes")}
            print(f"{query.mmss(t):>8}  {json.dumps(rest, ensure_ascii=False)}")
    return 0


def cmd_serve(args) -> int:
    import uvicorn

    from .server import create_app

    url = f"http://localhost:{args.port}"
    print(f"STRATA {__version__} -> {url}", file=sys.stderr)
    if args.open:
        _open(url)
    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="warning")
    return 0


def _open(url: str) -> None:
    for opener in (["wslview", url], ["cmd.exe", "/c", "start", url], ["xdg-open", url], ["open", url]):
        if shutil.which(opener[0]):
            import subprocess
            subprocess.Popen(opener, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return


def cmd_live(args) -> int:
    import time

    from .live import LiveSession

    a = _resolve(args.target)
    host, _, port = args.osc.rpartition(":")
    s = LiveSession(a, host or "127.0.0.1", int(port), fps=args.fps, listen=args.listen).start()
    s.clock.play(at=args.at)
    ctl = f", control on udp :{args.listen} (/strata/play|pause|seek)" if args.listen else ""
    print(f"live: {a['track']['title']} -> osc {args.osc} @ {args.fps} Hz from {args.at}s{ctl}. Ctrl-C to stop.",
          file=sys.stderr)
    try:
        while s.clock.time() < a["track"]["duration"] + 1 or args.listen:
            time.sleep(0.25)
    except KeyboardInterrupt:
        pass
    s.stop()
    return 0


def cmd_rm(args) -> int:
    from .library import Library

    lib = Library()
    for target in args.targets:
        a = _resolve(target)
        lib.delete(a["track"]["id"])
        print(f"removed {a['track']['title']} ({a['track']['id']}); source audio untouched")
    return 0


def cmd_backends(args) -> int:
    from .backends.base import registry

    for b in registry("full"):
        ok = b.available()
        flags = ("NC " if b.nc else "") + ("optional" if b.optional else "")
        print(f"{'ok ' if ok else '-- '} {b.name:<18} {','.join(b.dimensions):<14} {b.license:<34} {flags}")
        if not ok and getattr(b, "unavailable_reason", None):
            print(f"     {b.unavailable_reason}")
    return 0


def cmd_doctor(args) -> int:
    from .library import strata_home

    print(f"strata {__version__}  python {sys.version.split()[0]}")
    try:
        import torch
        gpu = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "none (CPU mode; slow)"
        print(f"torch {torch.__version__}  gpu: {gpu}")
    except ImportError:
        print("torch: NOT INSTALLED")
    home = strata_home()
    home.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(home).free / 1e9
    print(f"STRATA_HOME {home}  ({free:.0f} GB free)" + ("  [set STRATA_HOME to move it]" if "STRATA_HOME" not in os.environ else ""))
    web = Path(__file__).parent / "web" / "index.html"
    print(f"web ui: {'built' if web.exists() else 'NOT BUILT (cd ui && npm run build)'}")
    print("backends:")
    return cmd_backends(args)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="strata", description="Ensemble music analysis -> one JSON for edits, shows and code.")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("analyze", help="analyze audio files")
    a.add_argument("paths", nargs="+")
    a.add_argument("--profile", choices=["full", "commercial-safe"], default="full")
    a.add_argument("--fps", type=int, default=30, help="curve frame rate (24/25/30/60)")
    a.add_argument("--export", help="comma list of formats or 'all'")
    a.add_argument("--out", help="export directory (default: library exports dir)")
    a.add_argument("--device", help="cuda | cpu (default: auto)")
    a.add_argument("--force", action="store_true", help="ignore cached backend results")
    a.add_argument("--fast", action="store_true", help="skip optional extras (tags, lyrics)")
    a.set_defaults(fn=cmd_analyze)

    e = sub.add_parser("export", help="export an analysis")
    e.add_argument("target", help="analysis.json | audio file | track id | title")
    e.add_argument("--format", default="all")
    e.add_argument("--out")
    e.set_defaults(fn=cmd_export)

    q = sub.add_parser("query", help="ask an analysis questions")
    q.add_argument("target")
    g = q.add_mutually_exclusive_group()
    g.add_argument("--summary", action="store_true")
    g.add_argument("--at", type=float, metavar="SECONDS")
    g.add_argument("--sections", action="store_true")
    g.add_argument("--cues", action="store_true")
    g.add_argument("--beats", action="store_true")
    q.add_argument("--min", type=float, default=0.0, help="cue strength floor")
    q.add_argument("--type", help="cue types, comma list (section,drop,downbeat,accent)")
    q.add_argument("--from", dest="start", type=float, default=0.0)
    q.add_argument("--to", dest="end", type=float)
    q.add_argument("--downbeats", action="store_true")
    q.add_argument("--json", action="store_true")
    q.set_defaults(fn=cmd_query)

    s = sub.add_parser("serve", help="run the web UI")
    s.add_argument("--port", type=int, default=DEFAULT_PORT)
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--open", action="store_true")
    s.set_defaults(fn=cmd_serve)

    lv = sub.add_parser("live", help="play an analysis as OSC")
    lv.add_argument("target")
    lv.add_argument("--osc", default="127.0.0.1:9000", help="host:port")
    lv.add_argument("--at", type=float, default=0.0)
    lv.add_argument("--fps", type=int, default=60)
    lv.add_argument("--listen", type=int, help="udp port for /strata/play|pause|seek control")
    lv.set_defaults(fn=cmd_live)

    r = sub.add_parser("rm", help="remove tracks from the library (keeps source audio)")
    r.add_argument("targets", nargs="+", help="track id | audio file | title")
    r.set_defaults(fn=cmd_rm)

    sub.add_parser("backends", help="list backends").set_defaults(fn=cmd_backends)
    sub.add_parser("doctor", help="check the install").set_defaults(fn=cmd_doctor)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.fn(args) or 0
    except LookupError as e:
        print(f"strata: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
