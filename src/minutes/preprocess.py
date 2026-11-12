"""Step 1a: ffmpeg clean-up. Output is for the ASR only; the ORIGINAL file is what the dashboard plays
and what gets hashed (filters don't shift time, so timestamps line up)."""
from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path


def sha256_file(path: str | Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()


def build_ffmpeg_cmd(src: str, dst: str, denoise: bool = False) -> list[str]:
    # 16 kHz mono is what Whisper wants. Band-pass keeps the speech band (hum/rumble and hiss out).
    filters = ["highpass=f=100", "lowpass=f=7500"]
    if denoise:
        filters.append("afftdn=nf=-25")  # spectral denoise. OFF by default: it can hurt ASR, so A/B it.
    filters.append("loudnorm")
    return ["ffmpeg", "-y", "-i", src, "-ac", "1", "-ar", "16000", "-af", ",".join(filters), dst]


def preprocess(src: str | Path, dst: str | Path, denoise: bool = False) -> Path:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg not found. Install it (e.g. `sudo apt install ffmpeg`).")
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(build_ffmpeg_cmd(str(src), str(dst), denoise), check=True, capture_output=True)
    return Path(dst)
