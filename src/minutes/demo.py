"""`minutes demo`: a complete session with NO models, to try the dashboard and to test the trust rules.
It includes one fabricated quote and one invented line ID that the validator must drop, a low-confidence line,
and a decision-like Swahili line the 'LLM' missed (shown as a flag in the dashboard)."""
from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

from .pipeline import assemble_session
from .preprocess import sha256_file
from .schemas import Evidence, ExtractedAction, ExtractedDecision, ExtractedIssue, ExtractionResult, Line

RAW = [
    ("SPEAKER_00", 5, 12, "Good evening everyone, let's start with the water bills.", 0.93),
    ("SPEAKER_01", 13, 21, "The borehole pump failed again last month and we paid four thousand five hundred shillings to repair it.", 0.81),
    ("SPEAKER_02", 22, 27, "I propose we raise the monthly water levy from 300 to 500 shillings.", 0.55),
    ("SPEAKER_01", 28, 30, "I second the proposal.", 0.90),
    ("SPEAKER_00", 31, 38, "Objections? None. Then it is agreed, the levy is 500 shillings from March.", 0.88),
    ("SPEAKER_02", 40, 49, "Mrs. Kamau will collect the quotes from three plumbers before the next meeting.", 0.90),
    ("SPEAKER_01", 50, 58, "On the gate fee, I think visitors should not pay anything.", 0.85),
    ("SPEAKER_00", 59, 68, "No, no, the gate fee must stay, we need it for the guard's salary.", 0.47),
    ("SPEAKER_02", 69, 75, "Tumekubaliana kwamba tutapiga kura mwezi ujao kuhusu hilo.", 0.70),
    ("SPEAKER_00", 76, 80, "Let's move to security lights.", 0.92),
    ("SPEAKER_01", 81, 85, "The lights at the north gate are out again.", 0.89),
    ("SPEAKER_02", 86, 90, "Is the treasurer here tonight?", 0.91),
    ("SPEAKER_00", 91, 94, "Yes, I am here.", 0.94),
    ("SPEAKER_01", 95, 99, "Then please read the account balance.", 0.90),
    ("SPEAKER_00", 100, 106, "We have forty two thousand in the account.", 0.84),
    ("SPEAKER_02", 107, 110, "Thank you, meeting closed.", 0.93),
]


def _write_demo_audio(path: Path, seconds: int = 112) -> None:
    rate = 16000
    buf = bytearray(2 * rate * seconds)  # silence
    for s in {int(r[1]) for r in RAW}:  # a short beep where each line starts, so you can hear seeking work
        for n in range(int(0.15 * rate)):
            i = (s * rate + n) * 2
            buf[i:i + 2] = struct.pack("<h", int(6000 * math.sin(2 * math.pi * 440 * n / rate)))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(buf))


def fake_extraction() -> ExtractionResult:
    return ExtractionResult(
        decisions=[
            ExtractedDecision(text="Monthly water levy set to 500 shillings from March.",
                              evidence=[Evidence(line_id="L005", quote="it is agreed, the levy is 500 shillings from March")]),
            ExtractedDecision(text="Visitors will not pay the gate fee.",  # FABRICATED: nobody agreed this
                              evidence=[Evidence(line_id="L007", quote="visitors will not pay the gate fee")]),
            ExtractedDecision(text="Pump repair to be reimbursed.",  # INVENTED line id
                              evidence=[Evidence(line_id="L099", quote="the pump will be reimbursed")]),
        ],
        actions=[ExtractedAction(task="Collect quotes from three plumbers.", owner="Mrs. Kamau",
                                 evidence=[Evidence(line_id="L006", quote="Mrs. Kamau will collect the quotes from three plumbers")])],
        open_issues=[ExtractedIssue(topic="Whether visitors pay the gate fee",
                                    positions=["Visitors should not pay", "Fee must stay to fund the guard"],
                                    evidence=[Evidence(line_id="L007", quote="visitors should not pay anything"),
                                              Evidence(line_id="L008", quote="the gate fee must stay")])],
    )


def build_demo(runs_dir: str = "runs") -> Path:
    d = Path(runs_dir) / "demo"
    d.mkdir(parents=True, exist_ok=True)
    wav = d / "demo.wav"
    _write_demo_audio(wav)
    lines = [Line(id=f"L{i:03d}", start=s, end=e, speaker=sp, text=t, confidence=c) for i, (sp, s, e, t, c) in enumerate(RAW, 1)]
    s = assemble_session(lines, name="demo", audio=str(wav.resolve()), audio_sha256=sha256_file(wav),
                         asr_model="(demo)", language="en", extractor=lambda _: fake_extraction())
    out = d / "session.json"
    s.save(out)
    return out
