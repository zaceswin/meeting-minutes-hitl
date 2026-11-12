"""Step 1b: WhisperX transcription + alignment + (optional) pyannote diarization -> immutable Line IDs.

NOTE: WhisperX's API has moved between releases (DiarizationPipeline location, token kwarg name).
This module tries the known variants. If a call breaks on your version, this is the only file to fix.
"""
from __future__ import annotations

from .schemas import Line


def _diarization_pipeline(hf_token: str, device: str):
    import whisperx

    cls = getattr(whisperx, "DiarizationPipeline", None)
    if cls is None:
        from whisperx.diarize import DiarizationPipeline as cls  # newer releases
    try:
        return cls(use_auth_token=hf_token, device=device)
    except TypeError:
        return cls(token=hf_token, device=device)


def _line_confidence(seg: dict) -> float | None:
    """Mean alignment score over words. Words the aligner could not place (often numerals) count as 0.0,
    which deliberately drags lines containing amounts toward 'unreliable'. None if no word scores exist."""
    words = seg.get("words") or []
    if not words:
        return None
    scores = [float(w.get("score", 0.0)) for w in words]
    return round(sum(scores) / len(scores), 3)


def transcribe(
    wav: str,
    model_name: str = "large-v3",
    language: str | None = None,
    device: str = "cpu",
    compute_type: str = "int8",
    hf_token: str | None = None,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
    batch_size: int = 8,
) -> tuple[list[Line], str, list[str]]:
    import whisperx  # pip install ".[asr]"

    notes: list[str] = []
    audio = whisperx.load_audio(wav)
    model = whisperx.load_model(model_name, device, compute_type=compute_type, language=language)
    result = model.transcribe(audio, batch_size=batch_size)
    lang = result.get("language", language or "")

    try:
        align_model, meta = whisperx.load_align_model(language_code=lang, device=device)
        result = whisperx.align(result["segments"], align_model, meta, audio, device, return_char_alignments=False)
    except Exception as e:  # e.g. no alignment model for this language
        notes.append(f"Alignment unavailable for language '{lang}' ({e}); lines have NO confidence scores.")

    if hf_token:
        try:
            dia = _diarization_pipeline(hf_token, device)
            turns = dia(audio, min_speakers=min_speakers, max_speakers=max_speakers)
            result = whisperx.assign_word_speakers(turns, result)
        except Exception as e:
            notes.append(f"Diarization failed ({e}); speakers are unlabelled.")
    else:
        notes.append("No HF_TOKEN: diarization skipped; speakers are unlabelled.")

    lines = []
    for i, seg in enumerate(result["segments"], 1):
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        lines.append(
            Line(
                id=f"L{i:03d}",
                start=round(float(seg["start"]), 2),
                end=round(float(seg["end"]), 2),
                speaker=seg.get("speaker"),
                text=text,
                confidence=_line_confidence(seg),
            )
        )
    return lines, lang, notes
