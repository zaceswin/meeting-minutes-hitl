# meeting-minutes-hitl

Audio in, minutes out, **and nobody can say "that is not what we agreed"**, because every decision quotes the
transcript line it came from, plays the audio for that line, and nothing is shared until a human has reviewed it.

Built for a residents' association that records meetings on a phone passed around a noisy hall.

```
phone audio ─ffmpeg band-pass─▶ WhisperX (ASR + word alignment + pyannote speakers)
   ─▶ immutable [L001…] lines + confidence ─▶ SOURCE GATE (>15% unreliable? → manual mode, no LLM)
   ─▶ LLM, Pydantic-schema-constrained, must cite line_id + verbatim quote
   ─▶ VALIDATOR (drops any item whose quote isn't verbatim in its line)
   ─▶ FastAPI review dashboard (play audio per line, fix text, map speakers, accept/reject)
   ─▶ export: minutes.md (+ hashes) and decisions_register.csv   [refused while anything is pending]
```

## Try it in 2 minutes (no models, no API keys)
```bash
pip install -e ".[dev]"
minutes demo
minutes review demo        # open http://127.0.0.1:8000
pytest
```
The demo contains a fabricated quote and an invented line ID (both get dropped), a 47%-confidence line, and a
Swahili decision the "LLM" missed (marked ⚑ in the dashboard).

## Real run
```bash
sudo apt install ffmpeg
pip install -e ".[asr]"                      # WhisperX + torch: large download
export HF_TOKEN=...                          # accept the pyannote model terms on huggingface.co first
export ANTHROPIC_API_KEY=...                 # or EXTRACT_BACKEND=ollama for fully local extraction
minutes run meeting.m4a --name feb-2027 --model small --max-speakers 8      # CPU-friendly
minutes review feb-2027
minutes evaluate feb-2027 --reference my_typed_reference.txt --gold gold.json
```
No GPU? Use `--model small` or `medium`; add `--device cuda` if you have one. No `HF_TOKEN`? It still works, without speaker labels.

## Where I changed your design (on purpose)
| Original idea | What the code does | Why |
|---|---|---|
| Quote must be within a "string distance" of the line | **Exact** containment (ignoring case/punctuation); closeness shown only as a hint | `500` vs `600` is a 1-character edit. A fuzzy threshold would pass the exact error that starts disputes |
| Confidence from the model | Mean WhisperX **word-alignment** score; unaligned words (often numerals) score 0; no score = flagged `UNSCORED_AUDIO`, not silently trusted | ASR doesn't output one "confidence"; alignment score is the available signal. Needs your calibration |
| Validation error aborts | Bad items are **dropped and reported**; the retry feeds the schema error back once | One bad item shouldn't discard a good meeting; every drop is shown to the reviewer |
| Denoise first | Band-pass + loudness always; spectral denoise is **opt-in** (`--denoise`) | Denoising can hurt ASR; measure it with `minutes evaluate` before trusting it |
| Quote per decision | List of 1-3 evidence lines | A motion and its "carried" are usually two lines |

## New ideas included
- **⚑ Missed-decision finder**: lines that look like motions/votes (English + Swahili starter phrases) that no item cites. The quote check catches inventions; this catches omissions. It over-flags proposal/second lines; extend `MOTION_RE`.
- **Decisions register** (`decisions_register.csv`) with a blank `ratified_on` column: read it out and tick it at the next meeting so decisions stop being relitigated. CSV cells are protected against spreadsheet formula injection.
- **Tamper evidence**: minutes carry SHA-256 of the original recording and of the final transcript.
- **Self-filling error log**: every human correction is appended to `error_log.csv` with an error type.
- **Evaluation harness**: `minutes evaluate` gives WER, number accuracy, and item precision/recall against your gold file.
- **Local-only extraction** via Ollama, so resident speech never leaves the machine (untested; see below).
- **[docs/RECORDING_GUIDE.md](docs/RECORDING_GUIDE.md)**: spoken-motion procedure (chair repeats motions, names owners, reads decisions back). Often the biggest accuracy gain costs nothing.

## Trust rule
See [docs/TRUST_RULE.md](docs/TRUST_RULE.md). Thresholds (15% / 0.6) are starting guesses: your test meeting should justify or replace them.

## What is verified and what is not
- **Verified (26 tests + live server smoke test):** schemas, trust rules, validator, gate, flags, export blocking, register/CSV safety, dashboard API (including audio Range requests and the 409 on mismatched quotes), metrics, demo.
- **NOT verified:** WhisperX transcription/alignment/diarization on real audio (its API changes between releases; `transcribe.py` is the only file that touches it); the Anthropic and Ollama calls; ffmpeg on a real file; whether Swahili has an alignment model in your WhisperX version (the code falls back to unscored lines and says so). Your first real run will find the rough edges. Log them in `docs/ERROR_LOG.md`.

## Limits worth knowing
- Diarization is weak with a passed-around phone in a noisy hall. Speaker names are a convenience; **owners are never trusted from speaker labels**.
- Long meetings go to the LLM in one call; for 3-hour recordings you may need chunking.
- The dashboard is single-user, local, no login (binds to 127.0.0.1). Do not expose it to a network.

## Privacy
Recordings of residents are personal data. Get consent, say who hears the audio and when it is deleted, keep `runs/` out of git (the `.gitignore` already does), and prefer `EXTRACT_BACKEND=ollama` if residents object to a cloud API. Kenya's Data Protection Act, 2019 applies to personal data processing; check its requirements for your association.

## Layout
`src/minutes/` `preprocess.py` ffmpeg · `transcribe.py` WhisperX · `extract.py` LLM · `trust.py` rules · `pipeline.py` orchestration · `review_app.py` + `templates/review.html` dashboard · `export.py` · `metrics.py` · `demo.py` · `cli.py`

MIT licensed.
