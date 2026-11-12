"""Pydantic models.

Two layers on purpose:
  * Extracted*  - the ONLY shape the LLM may return (its JSON schema is sent to the model).
  * Session/Item/Line - what the pipeline and the review dashboard persist.
The LLM never writes status, flags or hashes; code does.
"""
from __future__ import annotations

import datetime
import json
import os
import tempfile
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field

LINE_ID_PATTERN = r"^L\d{3,}$"
Kind = Literal["decision", "action", "open_issue"]
Status = Literal["pending", "accepted", "rejected"]
PREFIX = {"decision": "D", "action": "A", "open_issue": "O"}


# ---------------- what the LLM must return ----------------
class Evidence(BaseModel):
    line_id: str = Field(pattern=LINE_ID_PATTERN, description="ID of a transcript line, e.g. L012")
    quote: str = Field(min_length=4, description="Characters copied VERBATIM from that single line")


class ExtractedDecision(BaseModel):
    text: str = Field(min_length=5, description="One-sentence statement of what was decided")
    evidence: list[Evidence] = Field(min_length=1, max_length=3)


class ExtractedAction(BaseModel):
    task: str = Field(min_length=5)
    owner: Optional[str] = Field(
        default=None, description="Person named as taking the task. null if nobody was named. Never guess."
    )
    evidence: list[Evidence] = Field(min_length=1, max_length=3)


class ExtractedIssue(BaseModel):
    topic: str = Field(min_length=3)
    positions: list[str] = Field(default_factory=list, description="Short statement per side")
    evidence: list[Evidence] = Field(min_length=1, max_length=4)


class ExtractionResult(BaseModel):
    decisions: list[ExtractedDecision] = Field(default_factory=list)
    actions: list[ExtractedAction] = Field(default_factory=list)
    open_issues: list[ExtractedIssue] = Field(default_factory=list)


# ---------------- what we persist ----------------
class Line(BaseModel):
    id: str = Field(pattern=LINE_ID_PATTERN)  # immutable once assigned
    start: float
    end: float
    speaker: Optional[str] = None
    text: str
    machine_text: str = ""  # what the ASR produced; never edited
    confidence: Optional[float] = Field(default=None, ge=0, le=1)  # None = no score available
    unreliable: bool = False

    def model_post_init(self, __context) -> None:
        if not self.machine_text:
            self.machine_text = self.text


class Item(BaseModel):
    id: str
    kind: Kind
    text: str
    owner: Optional[str] = None
    owner_confirmed: bool = False
    positions: list[str] = Field(default_factory=list)
    evidence: list[Evidence]
    status: Status = "pending"
    flags: list[str] = Field(default_factory=list)
    origin: Literal["machine", "human"] = "machine"


class Session(BaseModel):
    name: str
    meeting_date: str = Field(default_factory=lambda: datetime.date.today().isoformat())
    audio: str
    audio_sha256: str = ""
    asr_model: str = ""
    language: str = ""
    mode: Literal["extracted", "manual_review_required"] = "extracted"
    unreliable_ratio: float = 0.0
    notes: list[str] = Field(default_factory=list)
    reviewer: str = ""
    speakers: dict[str, str] = Field(default_factory=dict)  # SPEAKER_02 -> "Mrs. Kamau"
    lines: list[Line]
    items: list[Item] = Field(default_factory=list)

    def lines_by_id(self) -> dict[str, Line]:
        return {l.id: l for l in self.lines}

    def next_item_id(self, kind: str) -> str:
        p = PREFIX[kind]
        n = 1 + max((int(i.id[1:]) for i in self.items if i.id.startswith(p) and i.id[1:].isdigit()), default=0)
        return f"{p}{n}"

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(self.model_dump_json(indent=2))
        os.replace(tmp, path)  # atomic: a crash never leaves half a session

    @classmethod
    def load(cls, path: str | Path) -> "Session":
        return cls.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))
