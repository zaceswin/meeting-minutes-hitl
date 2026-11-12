# When the summary may NOT be trusted

This is the rule the code enforces (`src/minutes/trust.py`). Thresholds are starting guesses:
replace them with values justified by YOUR error log (see `ERROR_LOG.md`).

## Level 1: the whole recording (blocks extraction)
If more than **15%** of transcript lines have confidence **< 0.6**, the LLM step is skipped.
The session opens as `[MANUAL REVIEW REQUIRED - EXCESSIVE NOISE]`: transcript only, and the secretary
adds items by hand from lines she has listened to.

Confidence = mean WhisperX word-alignment score for the line. Words the aligner could not place
(often numerals) score 0, so lines with amounts are pulled toward "unreliable" on purpose.
If alignment is unavailable (e.g. no alignment model for the language), lines have **no score**: they are
not counted unreliable, but every item citing them is flagged `UNSCORED_AUDIO` and needs an audio check.

## Level 2: each extracted item (blocks acceptance)
| Condition | Effect |
|---|---|
| Cited `line_id` does not exist, or quote is not verbatim inside that ONE line | Item dropped at extraction; if a line is later corrected and the quote stops matching, `QUOTE_MISMATCH` blocks acceptance |
| Cited line is unreliable / unscored | `UNRELIABLE_AUDIO` / `UNSCORED_AUDIO`: listen before accepting |
| Number, amount, date in text or quote | `NUMBER_OR_AMOUNT`: listen before accepting |
| Action owner not confirmed by a human | `OWNER_UNCONFIRMED`: speaker labels are never evidence |

## Level 3: what no automatic rule can catch (human duties)
- **Missed decisions.** The dashboard marks decision-like lines no item cites with ⚑ (English + Swahili starter phrases). It is a prompt, not a guarantee.
- **Wrong speaker.** Diarization is weakest in noisy halls with a passed phone. Confirm who said it from the audio.
- **Correct words, wrong meaning** (sarcasm, a joke, a retracted motion). Only a person hears this.

## Never trust, regardless of flags
A summary whose reviewer name is empty, or that was exported with items still pending. The exporter refuses both.
