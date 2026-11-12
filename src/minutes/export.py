"""Step 4b: export. Refuses to run until a human has resolved everything."""
from __future__ import annotations

import csv
import hashlib
import io
from pathlib import Path

from . import trust
from .schemas import Session

BANNER = "[MANUAL REVIEW REQUIRED - EXCESSIVE NOISE]"


def hms(sec: float) -> str:
    s = int(sec)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


def transcript_sha256(s: Session) -> str:
    blob = "\n".join(f"{l.id}|{l.start}|{l.end}|{l.speaker}|{l.text}" for l in s.lines)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def blockers(s: Session) -> list[str]:
    trust.refresh(s)
    out = []
    if not s.reviewer.strip():
        out.append("Enter the reviewer's name.")
    pending = [i.id for i in s.items if i.status == "pending"]
    if pending:
        out.append(f"{len(pending)} item(s) still pending: {', '.join(pending)}")
    bad = [i.id for i in s.items if i.status == "accepted" and "QUOTE_MISMATCH" in i.flags]
    if bad:
        out.append(f"Accepted item(s) whose quote no longer matches the transcript: {', '.join(bad)} (re-quote or reject)")
    return out


def speaker_name(s: Session, label: str | None) -> str:
    if not label:
        return "unidentified speaker"
    return s.speakers.get(label) or label


def _cite(s: Session, item) -> list[str]:
    by = s.lines_by_id()
    out = []
    for ev in item.evidence:
        l = by[ev.line_id]
        q = " ".join(ev.quote.split())
        out.append(f"> “{q}” — {speaker_name(s, l.speaker)}, {ev.line_id} @ {hms(l.start)}")
    return out


def render_markdown(s: Session, include_transcript: bool = False) -> str:
    manual = s.mode == "manual_review_required"
    out = [f"# Meeting minutes — {s.name}", ""]
    if manual:
        out += [f"**{BANNER}**", f"{s.unreliable_ratio:.0%} of lines had unreliable audio. Treat the transcript as an aid, not a record.", ""]
    out += [
        f"- Meeting date: {s.meeting_date}",
        f"- Reviewed by: {s.reviewer or '(not set)'}",
        f"- Recording SHA-256: `{s.audio_sha256 or 'n/a'}`",
        f"- Transcript SHA-256: `{transcript_sha256(s)}`",
        "",
    ]
    for title, kind in (("Decisions", "decision"), ("Actions", "action"), ("Left open (NOT decided)", "open_issue")):
        out += [f"## {title}", ""]
        acc = [i for i in s.items if i.kind == kind and i.status == "accepted"]
        if not acc:
            out += ["_None recorded._", ""]
        for i in acc:
            extra = f" — **Owner: {i.owner or 'UNASSIGNED'}**" if kind == "action" else ""
            out.append(f"**{i.id}.** {i.text}{extra}")
            for p in i.positions:
                out.append(f"  - {p}")
            out += _cite(s, i)
            out.append("")
    if include_transcript or manual:
        out += ["## Transcript", ""]
        out += [f"- `{l.id}` {hms(l.start)} **{speaker_name(s, l.speaker)}**: {' '.join(l.text.split())}" for l in s.lines]
        out.append("")
    out += ["---", "Every item quotes the transcript line it came from. In a dispute, play the recording at that timestamp.",
            "Items rejected or not extracted are absent by design; the recording is the record.", ""]
    return "\n".join(out)


def _csv_safe(v: str) -> str:
    return "'" + v if v[:1] in "=+-@\t\r" else v  # block spreadsheet formula injection


def render_register(s: Session) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "meeting_date", "kind", "text", "owner", "speaker", "line_id", "timestamp", "quote", "reviewer", "ratified_on"])
    by = s.lines_by_id()
    for i in s.items:
        if i.status != "accepted":
            continue
        ev = i.evidence[0]
        l = by[ev.line_id]
        w.writerow([_csv_safe(str(v)) for v in (i.id, s.meeting_date, i.kind, i.text, i.owner or "",
                                                 speaker_name(s, l.speaker), ev.line_id, hms(l.start), ev.quote, s.reviewer, "")])
    return buf.getvalue()


def write_outputs(s: Session, out_dir: str | Path, include_transcript: bool = False) -> dict[str, str]:
    reasons = blockers(s)
    if reasons:
        raise ValueError("; ".join(reasons))
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    md, reg = out / "minutes.md", out / "decisions_register.csv"
    md.write_text(render_markdown(s, include_transcript), encoding="utf-8")
    reg.write_text(render_register(s), encoding="utf-8", newline="")
    return {"minutes": str(md), "register": str(reg)}
