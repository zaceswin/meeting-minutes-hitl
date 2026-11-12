# Error log: what the machine got wrong

`runs/<name>/error_log.csv` fills itself every time the reviewer corrects a line in the dashboard
(`when, line_id, speaker, machine_said, corrected_to, error_type`). This file is the human summary
you write after each test meeting. Commit the **summary**, never the recording or transcript.

## Test recording
- Date / place / people / duration:
- Phone, placement, background noise:
- Model, device, denoise on/off, diarization on/off:

## Measurements (`minutes evaluate NAME --reference ref.txt --gold gold.json`)
| Metric | Value | Notes |
|---|---|---|
| Word error rate (whole recording) | | |
| Numbers heard correctly | x / y | |
| Machine decisions: precision / recall | | |
| Machine actions: precision / recall | | |
| Lines flagged unreliable | % | gate limit 15% |
| Decisions the machine missed (added by hand) | | |

## Errors by type (count from error_log.csv)
| Type | Count | Example (machine -> correct) | Did a flag warn the reviewer? |
|---|---|---|---|
| number | | | |
| name | | | |
| mishear | | | |
| language (Swahili/English switch) | | | |
| crosstalk / dropped speech | | | |
| wrong speaker | | | |
| invented or wrong decision | | | |

## What changes next
- Threshold changes (and the evidence for them):
- Recording-procedure changes:
