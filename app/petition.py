"""Build the Petition object from the DATABASE (admin-entered data) over the YAML seed.

`config/petition.yaml` supplies constants (county, statutes, layout defaults, links);
everything variable — dates, resolution text, proponents, gist, ballot title, captain —
comes from the Settings table, edited on /admin/petition. Every server-side document
render goes through from_db() so the PDFs always match what the admin shows."""
from __future__ import annotations
import json
from sqlalchemy.orm import Session
from toolkit import config as cfg
from .settings import Settings


def proponents_from_settings(s: Settings) -> list[dict]:
    raw = s.raw("proponents")
    if not raw:
        return []
    try:
        rows = json.loads(raw)
    except ValueError:
        return []
    return [r for r in rows if isinstance(r, dict) and (r.get("name") or "").strip()][:3]


def from_db(db: Session, base: cfg.Petition | None = None) -> cfg.Petition:
    p = base or cfg.load()
    s = Settings(db, p)
    m = p.measure
    m.resolution_number = s.raw("resolution_number") or m.resolution_number
    m.title = s.raw("resolution_title") or m.title
    m.adoption_date = s.adoption_date or m.adoption_date
    if s.raw("measure_text"):
        m.exact_text_override = s.raw("measure_text")
    p.election.date = s.election_date or p.election.date
    if s.raw("gist"):
        p.gist = " ".join(s.raw("gist").split())
    if s.raw("ballot_title"):
        p.ballot_title = " ".join(s.raw("ballot_title").split())
    props = proponents_from_settings(s)
    if props:
        p.proponents = props
    if s.raw("captain_name") or s.raw("captain_phone"):
        p.contacts["petition_captain"] = {"name": s.raw("captain_name"), "phone": s.raw("captain_phone")}
    rv = s.registered_voters
    if rv:
        p.threshold.registered_voters = rv
        p.threshold.registered_voters_source = s.raw("registered_voters_source") or p.threshold.registered_voters_source
    p.layout.rows_per_sheet = s.rows_per_sheet
    p.layout.sheets_per_pamphlet = s.sheets_per_pamphlet
    if s.raw("duplex") in ("long-edge", "short-edge"):
        p.layout.duplex = s.raw("duplex")
    return p
