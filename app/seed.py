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


def _placeholder(*vals) -> bool:
    return any("[" in str(v) for v in vals if v)


def seed_pamphlets(db, count: int, sheets: int) -> dict:
    """Pre-create the print run P-001..P-<count> with <sheets> blank sheets each. Idempotent:
    existing numbers are left untouched (their sheets are topped up if short)."""
    out = {"pamphlets": 0, "sheets": 0}
    have = {p.number: p for p in db.scalars(select(m.Pamphlet)).all()}
    for n in range(1, count + 1):
        num = f"P-{n:03d}"
        p = have.get(num)
        if p is None:
            p = m.Pamphlet(number=num, status="Ready to Print"); db.add(p); out["pamphlets"] += 1
        existing = {sh.sheet_no for sh in p.sheets}
        for k in range(1, sheets + 1):
            if k not in existing:
                p.sheets.append(m.Sheet(sheet_no=k, status="Blank")); out["sheets"] += 1
    db.commit()
    return out


def seed_polling_places(db) -> dict:
    """Load the county's polling places (data/polling_places.csv) as HIDDEN candidate signing
    locations: one per venue (some venues serve two precincts), public=False, status=planned.
    Flip one to public in admin once the venue agrees and hours are set."""
    import csv
    from collections import OrderedDict
    out = {"locations": 0}
    path = ROOT / "data" / "polling_places.csv"
    if not path.exists():
        return out
    venues: "OrderedDict[tuple, dict]" = OrderedDict()
    for r in csv.DictReader(path.open()):
        key = re.sub(r"[^a-z0-9]", "", r["polling_place"].lower())   # same venue, addresses spelled differently
        v = venues.setdefault(key, {"row": r, "precincts": []})
        v["precincts"].append(int(r["precinct"]))
    for v in venues.values():
        r, pcts = v["row"], v["precincts"]
        slug = f"polling-{pcts[0]:02d}"
        if db.scalar(select(m.Location).where(m.Location.slug == slug)):
            continue
        lat = float(r["lat"]) if r.get("lat") else None
        lon = float(r["lon"]) if r.get("lon") else None
        served = ", ".join(str(p) for p in pcts)
        db.add(m.Location(slug=slug, name=r["polling_place"], address=r["address"], city=r["city"], lat=lat, lon=lon,
                          precinct=str(pcts[0]), status="planned", public=False,
                          notes=f"Election Board polling place for precinct{'s' if len(pcts) > 1 else ''} {served}. "
                                f"Candidate signing site — get the venue's permission, set hours, then mark public."
                                + ("" if lat else " Address did not geocode; use the Geocode button or enter coordinates.")))
        out["locations"] += 1
    db.commit()
    return out


def prune_examples(db) -> dict:
    """Remove seed cruft: example locations/events and bracketed placeholder contacts."""
    out = {"locations": 0, "events": 0, "contacts": 0}
    for e in db.scalars(select(m.Event)).all():
        if "example" in (e.notes or "").lower():
            db.delete(e); out["events"] += 1
    for l in db.scalars(select(m.Location)).all():
        if l.slug == "example-stipe-center" or "example" in (l.notes or "").lower() or "(example" in (l.name or "").lower():
            out["events"] += len(l.events); db.delete(l); out["locations"] += 1
    for c in db.scalars(select(m.Contact)).all():
        if _placeholder(c.name, c.phone):
            db.delete(c); out["contacts"] += 1
    db.commit()
    return out


def status(db) -> dict:
    """Row counts for a quick production sanity check (`python -m app.seed --status`)."""
    from sqlalchemy import func
    c = lambda model, **flt: db.scalar(select(func.count()).select_from(model).filter_by(**flt)) or 0
    return {"pamphlets": c(m.Pamphlet), "sheets": c(m.Sheet), "circulators": c(m.Circulator), "signups_new": c(m.VolunteerSignup, status="New"),
            "issues": c(m.Issue), "locations": c(m.Location), "locations_public": c(m.Location, public=True), "events": c(m.Event),
            "contacts_public": c(m.Contact, public=True), "qa_tasks": c(m.QATask), "records": c(m.RecordsLog), "users": c(m.User),
            "settings": c(m.Setting)}


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

    # contacts — first run only: once the captain manages them in admin, deploys must not re-add rows
    have = {(c.role, c.name) for c in db.scalars(select(m.Contact)).all()}
    cpath = ROOT / "data" / "contacts.yaml"
    if cpath.exists() and not have:
        for i, c in enumerate((yaml.safe_load(cpath.read_text()) or {}).get("contacts", [])):
            key = (c.get("role"), c.get("name"))
            if key in have or not c.get("role"):
                continue
            db.add(m.Contact(role=c["role"], name=c.get("name"), phone=str(c.get("phone")) if c.get("phone") else None,
                             email=c.get("email"), address=c.get("address"), hours=c.get("hours"),
                             public=bool(c.get("public", True)) and not _placeholder(c.get("name"), c.get("phone")),
                             sort_order=(i + 1) * 10))
            out["contacts"] += 1
    # never show bracketed placeholders ("[NAME]", "[PHONE]") on the public site
    for c in db.scalars(select(m.Contact).where(m.Contact.public.is_(True))).all():
        if _placeholder(c.name, c.phone):
            c.public = False

    # locations + events
    lpath, epath = ROOT / "data" / "signing_locations.yaml", ROOT / "data" / "events.yaml"
    loc_by_yaml_id: dict[str, m.Location] = {}
    first_run_locations = db.scalar(select(m.Location).limit(1)) is None
    if lpath.exists() and first_run_locations:
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
    if epath.exists() and first_run_locations:
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

    # QA tasks — first run only
    have_tasks = {t.task for t in db.scalars(select(m.QATask)).all()}
    for i, t in enumerate(QA_TASKS if not have_tasks else []):
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
    ap.add_argument("--pamphlets", nargs="?", const=-1, type=int, metavar="N",
                    help="pre-create the print run P-001..P-N (default N = Settings print_run)")
    ap.add_argument("--sheets", type=int, help="sheets per pamphlet (default = Settings sheets_per_pamphlet)")
    ap.add_argument("--polling-places", action="store_true", help="load polling places as hidden candidate signing locations")
    ap.add_argument("--status", action="store_true", help="print row counts and exit (no changes)")
    ap.add_argument("--prune-examples", action="store_true", help="delete example locations/events and placeholder contacts")
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE", help="set a Settings value (repeatable), e.g. --set overcollect_fraction=0.6")
    a = ap.parse_args(argv)
    dbmod.init_db()
    if a.set:
        with dbmod.SessionLocal() as db:
            st = Settings(db)
            for kv in a.set:
                k, _, v = kv.partition("=")
                if k not in DEFAULTS:
                    raise SystemExit(f"unknown setting: {k} (known: {', '.join(sorted(DEFAULTS))})")
                st.set(k, v)
                print(f"set {k} = {v!r}")
            db.commit()
            st = Settings(db)
            print("now: registered_voters", st.registered_voters, "| legal_minimum", st.legal_minimum, "| target", st.target_signatures)
        return
    if a.prune_examples:
        with dbmod.SessionLocal() as db:
            print("pruned:", prune_examples(db))
        return
    if a.status:
        with dbmod.SessionLocal() as db:
            st = Settings(db)
            print("status:", {**status(db), "legal_minimum": st.legal_minimum, "target": st.target_signatures})
        return
    with dbmod.SessionLocal() as db:
        out = seed(db, a.admin_user, a.admin_password)
        if a.pamphlets is not None:
            st = Settings(db)
            n = a.pamphlets if a.pamphlets > 0 else st.print_run
            out.update(seed_pamphlets(db, n, a.sheets or st.sheets_per_pamphlet))
        if a.polling_places:
            out["polling_places"] = seed_polling_places(db)["locations"]
    print("seeded:", out)


if __name__ == "__main__":
    main()
