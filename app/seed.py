"""Idempotent seed: settings defaults (only where absent), contacts, locations/events from
data/*.yaml, the Filing QA checklist, and the first admin user.

    python -m app.seed [--admin-user U --admin-password P]
    ADMIN_USER / ADMIN_PASSWORD env vars work too (used by Dokku postdeploy)."""
from __future__ import annotations
import argparse, os, re, sys
from datetime import date, time
import yaml
from sqlalchemy import select
from toolkit import ROOT, config as cfg
from . import db as dbmod
from . import models as m
from .auth import hash_password
from .settings import Settings, DEFAULTS

QA_TASKS = [
    "Get the exact adopted resolution (file-stamped/certified) with all attachments after the Board votes",
    "Insert the exact resolution number, title, adoption date and full adopted text into config + measure/",
    "Get the written registered-voter count from the County Election Board; calculate the 10% minimum",
    "Finalize petition text, gist and ballot title; run `make final` (no placeholders)",
    "Attorney review of wording, ballot title and pamphlet layout",
    "Confirm filing location, deadline and next general county election date with the Election Board",
    "File the true copy (and ballot title) with the Secretary of the County Election Board before circulation",
    "Get file-stamped copies with date/time/person; log them in the Records log",
    "Run `make freeze`; give the print vendor the frozen PDF and its hash",
    "Print pamphlets; number them; record print batch + hash on each pamphlet record",
    "Verify every circulator's Oklahoma voter registration and record training before issuing pamphlets",
    "Issue and track every pamphlet; daily returns to the Petition Captain",
    "Notarize affidavits after collection; check seal, signature, commission number and expiration",
    "Audit every sheet against the E1–E8 defect codes; open issues for anything questionable",
    "File signed pamphlets before the 30-day deadline; get a receipt; log it",
    "Watch for the newspaper notice and the 10-day protest window; keep all records together",
]


def _slug(v: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (v or "").lower()).strip("-")[:60] or "location"


def seed(db, admin_user: str | None = None, admin_password: str | None = None) -> dict:
    out = {"settings": 0, "contacts": 0, "locations": 0, "events": 0, "qa_tasks": 0, "users": 0}
    petition = cfg.load()
    s = Settings(db, petition)
    existing = {row.key for row in db.scalars(select(m.Setting)).all()}
    for key in DEFAULTS:
        if key not in existing:
            val = s.raw(key)  # DEFAULTS or config-derived
            db.add(m.Setting(key=key, value=val))
            out["settings"] += 1
    db.flush()

    # contacts
    have = {(c.role, c.name) for c in db.scalars(select(m.Contact)).all()}
    cpath = ROOT / "data" / "contacts.yaml"
    if cpath.exists():
        for i, c in enumerate((yaml.safe_load(cpath.read_text()) or {}).get("contacts", [])):
            key = (c.get("role"), c.get("name"))
            if key in have or not c.get("role"):
                continue
            db.add(m.Contact(role=c["role"], name=c.get("name"), phone=str(c.get("phone")) if c.get("phone") else None,
                             email=c.get("email"), address=c.get("address"), hours=c.get("hours"),
                             public=bool(c.get("public", True)), sort_order=(i + 1) * 10))
            out["contacts"] += 1

    # locations + events
    lpath, epath = ROOT / "data" / "signing_locations.yaml", ROOT / "data" / "events.yaml"
    loc_by_yaml_id: dict[str, m.Location] = {}
    if lpath.exists():
        for l in (yaml.safe_load(lpath.read_text()) or {}).get("locations", []):
            slug = _slug(l.get("id") or l.get("name"))
            row = db.scalar(select(m.Location).where(m.Location.slug == slug))
            if row is None:
                is_example = "example" in (l.get("notes") or "").lower() or "example" in (l.get("name") or "").lower()
                row = m.Location(slug=slug, name=l.get("name") or slug, address=l.get("address"), city=l.get("city"),
                                 zip=str(l.get("zip")) if l.get("zip") else None, lat=l.get("lat"), lon=l.get("lon"),
                                 status=l.get("status") or "planned", hours=l.get("hours"), notes=l.get("notes"),
                                 public=not is_example)
                db.add(row); out["locations"] += 1
            loc_by_yaml_id[l.get("id") or slug] = row
        db.flush()
    if epath.exists():
        for e in (yaml.safe_load(epath.read_text()) or {}).get("events", []):
            loc = loc_by_yaml_id.get(e.get("location_id"))
            if loc is None:
                continue
            d = e.get("date")
            d = date.fromisoformat(str(d)) if d else None
            exists = db.scalar(select(m.Event).where(m.Event.location_id == loc.id, m.Event.date == d))
            if exists:
                continue
            is_example = "example" in (e.get("notes") or "").lower()
            db.add(m.Event(location_id=loc.id, date=d, start=time.fromisoformat(e["start"]) if e.get("start") else None,
                           end=time.fromisoformat(e["end"]) if e.get("end") else None, notes=e.get("notes"),
                           public=not is_example and d is not None))
            out["events"] += 1

    # QA tasks
    have_tasks = {t.task for t in db.scalars(select(m.QATask)).all()}
    for i, t in enumerate(QA_TASKS):
        if t not in have_tasks:
            db.add(m.QATask(task=t, sort_order=(i + 1) * 10)); out["qa_tasks"] += 1

    # first admin user
    admin_user = admin_user or os.environ.get("ADMIN_USER")
    admin_password = admin_password or os.environ.get("ADMIN_PASSWORD")
    if admin_user and admin_password and not db.scalar(select(m.User).limit(1)):
        if len(admin_password) < 10:
            print("ADMIN_PASSWORD must be at least 10 characters; no user created.", file=sys.stderr)
        else:
            db.add(m.User(username=admin_user, password_hash=hash_password(admin_password), role="admin")); out["users"] += 1
    db.commit()
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--admin-user"); ap.add_argument("--admin-password")
    a = ap.parse_args(argv)
    dbmod.init_db()
    with dbmod.SessionLocal() as db:
        out = seed(db, a.admin_user, a.admin_password)
    print("seeded:", out)


if __name__ == "__main__":
    main()
