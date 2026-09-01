"""Server-side document generation: render with WeasyPrint into a temp dir, run the statutory
checks, store the PDFs + reports in Postgres (DocumentBuild/DocumentFile). One build at a time."""
from __future__ import annotations
import json
import tempfile
import threading
import traceback
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import select
from . import models as m
from .db import SessionLocal
from .petition import from_db

_lock = threading.Lock()


def _snapshot(p) -> str:
    f = p.fmt
    return json.dumps({"county": p.county, "resolution_number": f.resolution_number, "adoption_date": f.adoption_date,
                       "filing_deadline": f.filing_deadline, "election_date": f.election_date,
                       "registered_voters": f.registered_voters, "legal_minimum": f.legal_minimum, "target": f.target_signatures,
                       "rows_per_sheet": p.layout.rows_per_sheet, "sheets_per_pamphlet": p.layout.sheets_per_pamphlet,
                       "placeholders": p.placeholders})


def _run(build_id: int, kind: str, session_factory) -> None:
    from toolkit.docs.build import build_all, write_manifest, PlaceholderError
    from toolkit.docs.check import run_checks, load, sha256, content_fingerprint
    db = session_factory()
    try:
        b = db.get(m.DocumentBuild, build_id)
        p = from_db(db)
        b.duplex = p.layout.duplex
        b.petition_snapshot = _snapshot(p)
        with tempfile.TemporaryDirectory() as td:
            paths = build_all(td, final=(kind == "final"), duplex=p.layout.duplex, petition=p)
            write_manifest(td, paths, final=(kind == "final"), duplex=p.layout.duplex, petition=p)
            results = run_checks(td, final=(kind == "final"), petition=p)
            b.manifest = (Path(td) / "manifest.json").read_text()
            b.check_report = json.dumps([{"doc": r.doc, "check": r.check, "ok": r.ok, "detail": r.detail} for r in results])
            for path in paths:
                data = path.read_bytes()
                pages = load(path)
                db.add(m.DocumentFile(build_id=build_id, name=path.name, pages=len(pages), bytes_len=len(data),
                                      sha256=sha256(path), content=data))
                if path.name == "01-petition-pamphlet.pdf":
                    b.pamphlet_sha256 = sha256(path)
                    b.pamphlet_fingerprint = content_fingerprint(pages)
        b.status = "ok"
        db.commit()
        prune(db)
    except PlaceholderError as e:
        db.rollback(); b = db.get(m.DocumentBuild, build_id)
        b.status, b.error = "failed", str(e); db.commit()
    except Exception:
        db.rollback(); b = db.get(m.DocumentBuild, build_id)
        b.status, b.error = "failed", traceback.format_exc()[-4000:]; db.commit()
    finally:
        db.close()
        _lock.release()


def start_build(kind: str, user: str, session_factory=None, wait: bool = False) -> tuple[int | None, str | None]:
    """Returns (build_id, error). Refuses if a build is already running."""
    assert kind in ("draft", "final")
    session_factory = session_factory or SessionLocal
    if not _lock.acquire(blocking=False):
        return None, "A build is already running — wait for it to finish."
    db = session_factory()
    try:
        if kind == "final":
            left = from_db(db).placeholders
            if left:
                _lock.release()
                return None, "Final build refused — placeholders remain: " + "; ".join(left)
        b = m.DocumentBuild(kind=kind, built_by=user, built_at=datetime.now(timezone.utc))
        db.add(b); db.commit()
        bid = b.id
    except Exception:
        _lock.release(); raise
    finally:
        db.close()
    t = threading.Thread(target=_run, args=(bid, kind, session_factory), daemon=True)
    t.start()
    if wait:
        t.join(timeout=600)
    return bid, None


def list_builds(db, limit: int = 20) -> list[m.DocumentBuild]:
    from sqlalchemy.orm import selectinload
    return list(db.scalars(select(m.DocumentBuild).options(selectinload(m.DocumentBuild.files))
                           .order_by(m.DocumentBuild.id.desc()).limit(limit)))


def prune(db, keep: int = 20) -> int:
    rows = list(db.scalars(select(m.DocumentBuild).order_by(m.DocumentBuild.id.desc())))
    excess = [b for b in rows[keep:] if not b.filed]
    drafts_over = [b for b in rows[:keep] if b.kind == "draft" and not b.filed]
    # beyond `keep`, drop everything unfiled; within, nothing
    removed = 0
    for b in excess:
        db.delete(b); removed += 1
    if removed:
        db.commit()
    return removed
