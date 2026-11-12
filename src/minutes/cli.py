from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import export, metrics
from .schemas import Session


def _session_path(runs_dir: str, name: str) -> Path:
    p = Path(runs_dir) / name / "session.json"
    if not p.exists():
        sys.exit(f"No session at {p}. Run `minutes run` or `minutes demo` first.")
    return p


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="minutes", description=__doc__)
    ap.add_argument("--runs-dir", default=os.environ.get("MINUTES_RUNS_DIR", "runs"))
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="audio -> session.json (needs ffmpeg + `pip install .[asr]`)")
    r.add_argument("audio")
    r.add_argument("--name", required=True)
    r.add_argument("--model", default="large-v3", help="e.g. small for CPU-only laptops")
    r.add_argument("--language", default=None, help="en, sw ... (default: auto-detect)")
    r.add_argument("--device", default="cpu", choices=["cpu", "cuda"])
    r.add_argument("--compute-type", default=None)
    r.add_argument("--denoise", action="store_true", help="ffmpeg denoise (A/B test it; can hurt accuracy)")
    r.add_argument("--no-diarize", action="store_true")
    r.add_argument("--min-speakers", type=int)
    r.add_argument("--max-speakers", type=int)
    r.add_argument("--backend", default=os.environ.get("EXTRACT_BACKEND", "anthropic"), choices=["anthropic", "ollama"])

    v = sub.add_parser("review", help="open the review dashboard")
    v.add_argument("name")
    v.add_argument("--host", default="127.0.0.1")
    v.add_argument("--port", type=int, default=8000)

    e = sub.add_parser("export", help="CLI export (same blocking rules as the dashboard)")
    e.add_argument("name")
    e.add_argument("--reviewer")
    e.add_argument("--include-transcript", action="store_true")

    sub.add_parser("demo", help="build a model-free demo session in runs/demo")

    ev = sub.add_parser("evaluate", help="score a session against a reference transcript / gold items")
    ev.add_argument("name")
    ev.add_argument("--reference", help="plain-text reference transcript you typed from the recording")
    ev.add_argument("--gold", help='JSON: {"decision":[["L005"]],"action":[["L006"]],"open_issue":[["L007","L008"]]}')

    a = ap.parse_args(argv)

    if a.cmd == "demo":
        from .demo import build_demo
        print(f"demo session: {build_demo(a.runs_dir)}\nnow run: minutes review demo")
    elif a.cmd == "run":
        from .pipeline import run
        run(a.audio, a.name, a.runs_dir, asr_model=a.model, language=a.language, device=a.device,
            compute_type=a.compute_type or ("float16" if a.device == "cuda" else "int8"),
            denoise=a.denoise, diarize=not a.no_diarize, min_speakers=a.min_speakers,
            max_speakers=a.max_speakers, backend=a.backend, hf_token=os.environ.get("HF_TOKEN"))
    elif a.cmd == "review":
        import uvicorn
        from .review_app import create_app
        uvicorn.run(create_app(_session_path(a.runs_dir, a.name)), host=a.host, port=a.port)
    elif a.cmd == "export":
        p = _session_path(a.runs_dir, a.name)
        s = Session.load(p)
        if a.reviewer:
            s.reviewer = a.reviewer
        try:
            print(json.dumps(export.write_outputs(s, p.parent, a.include_transcript), indent=2))
        except ValueError as ex:
            sys.exit(f"BLOCKED: {ex}")
    elif a.cmd == "evaluate":
        s = Session.load(_session_path(a.runs_dir, a.name))
        if a.reference:
            ref = Path(a.reference).read_text(encoding="utf-8")
            machine = " ".join(l.machine_text for l in s.lines)
            print("ASR vs reference:", json.dumps(metrics.wer(ref, machine)))
            print("numbers:", json.dumps(metrics.number_recall(ref, machine)))
        if a.gold:
            print("items:", json.dumps(metrics.item_scores(s, json.loads(Path(a.gold).read_text())), indent=2))
