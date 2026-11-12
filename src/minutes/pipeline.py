"""Orchestrator. `assemble_session` is model-free (takes lines + an extractor) so it is testable and reusable."""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from . import trust
from .preprocess import preprocess, sha256_file
from .schemas import ExtractionResult, Line, Session


def assemble_session(
    lines: list[Line],
    *,
    name: str,
    audio: str,
    audio_sha256: str = "",
    asr_model: str = "",
    language: str = "",
    notes: Optional[list[str]] = None,
    extractor: Optional[Callable[[list[Line]], ExtractionResult]] = None,
) -> Session:
    trust.mark_unreliable(lines)
    gate = trust.source_gate(lines)
    s = Session(name=name, audio=audio, audio_sha256=audio_sha256, asr_model=asr_model, language=language,
                lines=lines, unreliable_ratio=gate.ratio, notes=list(notes or []))
    if gate.n_lines and gate.n_unscored / gate.n_lines > 0.5:
        s.notes.append("More than half of the lines have NO confidence score: every item needs an audio check.")
    if not gate.ok:
        s.mode = "manual_review_required"
        s.notes.append(
            f"[MANUAL REVIEW REQUIRED - EXCESSIVE NOISE] {gate.n_unreliable}/{gate.n_lines} lines "
            f"({gate.ratio:.0%}) are unreliable (limit {trust.MAX_UNRELIABLE_RATIO:.0%}). LLM extraction skipped."
        )
    elif extractor is not None:
        res = extractor(lines)
        s.items, problems = trust.items_from_extraction(res, s)
        s.notes += [f"VALIDATOR {p}" for p in problems]
    trust.refresh(s)
    return s


def run(
    audio: str,
    name: str,
    runs_dir: str = "runs",
    *,
    asr_model: str = "large-v3",
    language: str | None = None,
    device: str = "cpu",
    compute_type: str = "int8",
    denoise: bool = False,
    diarize: bool = True,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
    backend: str = "anthropic",
    hf_token: str | None = None,
    log: Callable[[str], None] = print,
) -> Path:
    from .extract import run_extraction
    from .transcribe import transcribe

    run_dir = Path(runs_dir) / name
    run_dir.mkdir(parents=True, exist_ok=True)
    log("1/4 preprocessing audio (ffmpeg)")
    wav = preprocess(audio, run_dir / "processed.wav", denoise=denoise)
    log("2/4 transcribing + aligning + diarizing (WhisperX)")
    lines, lang, notes = transcribe(
        str(wav), asr_model, language, device, compute_type,
        hf_token if diarize else None, min_speakers, max_speakers,
    )
    log(f"3/4 {len(lines)} lines; checking source reliability")
    s = assemble_session(
        lines, name=name, audio=str(Path(audio).resolve()), audio_sha256=sha256_file(audio),
        asr_model=asr_model, language=lang, notes=notes,
        extractor=lambda ls: run_extraction(ls, backend),
    )
    path = run_dir / "session.json"
    s.save(path)
    log(f"4/4 mode={s.mode}; {len(s.items)} items; next: minutes review {name}")
    return path
