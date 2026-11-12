"""Step 4a: the human-in-the-loop gate (FastAPI). Local use only: binds to 127.0.0.1, has no login."""
from __future__ import annotations

import csv
import datetime
import mimetypes
import threading
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from . import export, trust
from .schemas import Evidence, Item, Kind, Session, Status

TEMPLATE = Path(__file__).parent / "templates" / "review.html"


class ItemPatch(BaseModel):
    status: Optional[Status] = None
    text: Optional[str] = None
    owner: Optional[str] = None
    requote: bool = False


class NewItem(BaseModel):
    kind: Kind
    text: str
    line_id: str
    owner: Optional[str] = None


class LinePatch(BaseModel):
    text: str
    error_type: str = "unspecified"


class ExportBody(BaseModel):
    reviewer: Optional[str] = None
    include_transcript: bool = False


def create_app(session_path: str | Path) -> FastAPI:
    path = Path(session_path)
    run_dir = path.parent
    lock = threading.RLock()
    st = {"s": Session.load(path)}
    app = FastAPI(title="Minutes review")

    def persist() -> Session:
        trust.refresh(st["s"])
        st["s"].save(path)
        return st["s"]

    def log_correction(line_id, speaker, before, after, error_type):
        f = run_dir / "error_log.csv"
        new = not f.exists()
        with open(f, "a", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            if new:
                w.writerow(["when", "line_id", "speaker", "machine_said", "corrected_to", "error_type"])
            w.writerow([datetime.datetime.now().isoformat(timespec="seconds"), line_id, speaker or "", before, after, error_type])

    @app.get("/", response_class=HTMLResponse)
    def index():
        return TEMPLATE.read_text(encoding="utf-8")

    @app.get("/api/session")
    def get_session():
        with lock:
            s = persist()
            return {
                "session": s.model_dump(),
                "uncovered": trust.uncovered_candidates(s),
                "blockers": export.blockers(s),
                "limits": {"unreliable_below": trust.UNRELIABLE_BELOW, "max_ratio": trust.MAX_UNRELIABLE_RATIO},
            }

    @app.get("/api/audio")
    def audio():
        p = Path(st["s"].audio)
        if not p.exists():
            raise HTTPException(404, f"Audio file not found: {p}")
        return FileResponse(p, media_type=mimetypes.guess_type(p.name)[0] or "application/octet-stream")

    @app.put("/api/speakers")
    def speakers(mapping: dict[str, str]):
        with lock:
            for k, v in mapping.items():
                if v.strip():
                    st["s"].speakers[k] = v.strip()
                else:
                    st["s"].speakers.pop(k, None)
            persist()
        return {"ok": True}

    @app.put("/api/lines/{line_id}")
    def edit_line(line_id: str, body: LinePatch):
        with lock:
            line = st["s"].lines_by_id().get(line_id)
            if line is None:
                raise HTTPException(404, "no such line")
            new = " ".join(body.text.split())
            if not new:
                raise HTTPException(422, "text cannot be empty")
            if new != line.text:
                log_correction(line_id, line.speaker, line.text, new, body.error_type)
                line.text = new
            persist()
        return {"ok": True}

    @app.patch("/api/items/{item_id}")
    def patch_item(item_id: str, p: ItemPatch):
        with lock:
            s = st["s"]
            it = next((i for i in s.items if i.id == item_id), None)
            if it is None:
                raise HTTPException(404, "no such item")
            if p.text is not None and p.text.strip():
                it.text = p.text.strip()
            if p.owner is not None:
                it.owner = p.owner.strip() or None
                it.owner_confirmed = True  # a human typed it
            if p.requote:
                by = s.lines_by_id()
                for ev in it.evidence:
                    ev.quote = by[ev.line_id].text
            persist()
            if p.status:
                if p.status == "accepted" and "QUOTE_MISMATCH" in it.flags:
                    raise HTTPException(409, "Quote does not match the transcript line. Re-quote it or reject the item.")
                it.status = p.status
                persist()
        return {"ok": True}

    @app.post("/api/items")
    def add_item(b: NewItem):
        with lock:
            s = st["s"]
            line = s.lines_by_id().get(b.line_id)
            if line is None:
                raise HTTPException(404, "no such line")
            if not b.text.strip():
                raise HTTPException(422, "text required")
            s.items.append(Item(
                id=s.next_item_id(b.kind), kind=b.kind, text=b.text.strip(), owner=(b.owner or None),
                owner_confirmed=bool(b.owner), evidence=[Evidence(quote=line.text, line_id=line.id)],
                status="accepted", origin="human",
            ))
            persist()
        return {"ok": True}

    @app.get("/api/preview")
    def preview():
        with lock:
            return {"blockers": export.blockers(st["s"]), "markdown": export.render_markdown(st["s"])}

    @app.post("/api/export")
    def do_export(b: ExportBody):
        with lock:
            if b.reviewer is not None:
                st["s"].reviewer = b.reviewer.strip()
                persist()
            try:
                return export.write_outputs(st["s"], run_dir, b.include_transcript)
            except ValueError as e:
                raise HTTPException(409, str(e))

    return app
