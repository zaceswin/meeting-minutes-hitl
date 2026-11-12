"""The trust rule, as code. Pure functions, no I/O, fully unit-tested.

Design decision: quotes are checked by EXACT (case/punctuation-insensitive) containment, not
fuzzy edit distance. An edit-distance threshold cannot tell "500" from "600" (they differ by
one character), and in a water-levy meeting that is exactly the error that starts a fight.
Closeness is reported only as a hint to the reviewer.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from .schemas import PREFIX, Evidence, ExtractionResult, Item, Line, Session

UNRELIABLE_BELOW = 0.6      # line confidence under this => [UNRELIABLE AUDIO]
MAX_UNRELIABLE_RATIO = 0.15  # more than this => skip the LLM, manual review

NUMBER_RE = re.compile(
    r"\d|\b(hundred|thousand|million|elfu|mia|laki|shilling|shillings|shilingi|bob|ksh|kes)\b", re.I
)
# Starter lists for catching decisions the LLM MISSED. Extend after reading your own transcripts.
MOTION_RE = re.compile(
    r"\b(i propose|propose that|i move|motion|seconded|i second|all in favou?r|carried|it passes|"
    r"it is agreed|we agreed|agreed that|resolved|let'?s vote|by show of hands|"
    r"tumekubaliana|tumekubali|imepitishwa|naunga mkono|nimeunga mkono|tupige kura|pendekezo|azimio)\b",
    re.I,
)


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s']", "", s.lower())).strip()


def quote_ok(quote: str, line_text: str) -> bool:
    """Quote must sit inside ONE line verbatim. Short quotes (<3 words) only count if they ARE the whole line."""
    q, s = norm(quote), norm(line_text)
    if not q:
        return False
    return q == s or (len(q.split()) >= 3 and q in s)


def closeness(quote: str, line_text: str) -> float:
    return round(SequenceMatcher(None, norm(quote), norm(line_text)).ratio(), 2)


# ---------- source-level gate ----------
@dataclass
class Gate:
    ok: bool
    ratio: float
    n_lines: int
    n_unreliable: int
    n_unscored: int


def mark_unreliable(lines: list[Line], threshold: float = UNRELIABLE_BELOW) -> None:
    for l in lines:
        l.unreliable = l.confidence is not None and l.confidence < threshold


def source_gate(lines: list[Line], max_ratio: float = MAX_UNRELIABLE_RATIO) -> Gate:
    n = len(lines)
    bad = sum(1 for l in lines if l.unreliable)
    unscored = sum(1 for l in lines if l.confidence is None)
    ratio = bad / n if n else 1.0
    return Gate(ok=n > 0 and ratio <= max_ratio, ratio=round(ratio, 3), n_lines=n, n_unreliable=bad, n_unscored=unscored)


# ---------- extraction-level validation ----------
def _evidence_problems(evs: list[Evidence], lines: dict[str, Line]) -> list[str]:
    out = []
    for ev in evs:
        line = lines.get(ev.line_id)
        if line is None:
            out.append(f"{ev.line_id}: line does not exist")
        elif not quote_ok(ev.quote, line.text):
            out.append(
                f"{ev.line_id}: quote not found verbatim (closeness {closeness(ev.quote, line.text)}): “{ev.quote}”"
            )
    return out


def items_from_extraction(res: ExtractionResult, session: Session) -> tuple[list[Item], list[str]]:
    """Convert LLM output to Items. Any item with unverifiable evidence is DROPPED and reported."""
    lines = session.lines_by_id()
    items: list[Item] = list(session.items)
    problems: list[str] = []

    def add(kind, text, evidence, owner=None, positions=None):
        bad = _evidence_problems(evidence, lines)
        if bad:
            problems.append(f"dropped {kind} “{text[:60]}”: " + "; ".join(bad))
            return
        tmp = Session(name=session.name, audio=session.audio, lines=session.lines, items=items)
        items.append(
            Item(id=tmp.next_item_id(kind), kind=kind, text=text, owner=owner, positions=positions or [], evidence=evidence)
        )

    for d in res.decisions:
        add("decision", d.text, d.evidence)
    for a in res.actions:
        add("action", a.task, a.evidence, owner=a.owner)
    for o in res.open_issues:
        add("open_issue", o.topic, o.evidence, positions=o.positions)
    return items, problems


# ---------- per-item flags (always recomputed from scratch, never stale) ----------
def compute_flags(item: Item, lines: dict[str, Line]) -> list[str]:
    flags: set[str] = set()
    for ev in item.evidence:
        line = lines.get(ev.line_id)
        if line is None or not quote_ok(ev.quote, line.text):
            flags.add("QUOTE_MISMATCH")
            continue
        if line.confidence is None:
            flags.add(f"UNSCORED_AUDIO:{ev.line_id}")
        elif line.unreliable:
            flags.add(f"UNRELIABLE_AUDIO:{ev.line_id}")
        if NUMBER_RE.search(ev.quote):
            flags.add("NUMBER_OR_AMOUNT")
    if NUMBER_RE.search(item.text):
        flags.add("NUMBER_OR_AMOUNT")
    if item.kind == "action" and item.owner and item.owner.upper() != "UNASSIGNED" and not item.owner_confirmed:
        flags.add("OWNER_UNCONFIRMED")
    if item.kind == "action" and not item.owner:
        flags.add("NO_OWNER")
    return sorted(flags)


def refresh(session: Session) -> None:
    by_id = session.lines_by_id()
    for it in session.items:
        it.flags = compute_flags(it, by_id)


def needs_audio_check(item: Item) -> bool:
    return any(not f.startswith("OWNER") and f != "NO_OWNER" for f in item.flags)


# ---------- recall helper: decision-like lines no item cites ----------
def candidate_lines(lines: list[Line]) -> list[str]:
    return [l.id for l in lines if MOTION_RE.search(l.text)]


def uncovered_candidates(session: Session) -> list[str]:
    cited = {ev.line_id for it in session.items for ev in it.evidence}
    return [i for i in candidate_lines(session.lines) if i not in cited]
