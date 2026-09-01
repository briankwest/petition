"""Typed access to the Setting table with defaults from config/petition.yaml.
Admin edits these; documents still read config/petition.yaml (the legal instrument is
built offline and frozen) — `toolkit.xlsx.export` and the site read the DB."""
from __future__ import annotations
from datetime import date, timedelta
from math import ceil
from sqlalchemy.orm import Session
from sqlalchemy import select
from toolkit import config as cfg
from .models import Setting

DEFAULTS = {
    "adoption_date": None, "election_date": None, "filing_deadline_override": None,
    "registered_voters": None, "registered_voters_source": None, "registered_voters_date": None,
    "print_run": "200", "sheets_per_pamphlet": None, "rows_per_sheet": None,
    "est_valid_rate": "0.85", "overcollect_fraction": None,
    "banner": "The County Commissioners tabled the resolution. No adoption date has been set. "
              "No signatures can be collected until the resolution is adopted and a true copy of the petition is filed.",
    "public_show_counts": "false", "public_show_progress": "false",
    "captain_name": None, "captain_phone": None, "site_status": "pre-adoption",
    "resolution_number": None, "resolution_title": None, "measure_text": None,
    "return_location": None, "daily_return_deadline": None,
    "gist": None, "ballot_title": None, "proponents": None,          # proponents: JSON list of {name,address,city,zip}
    "duplex": None,
    "petition_frozen": "false", "frozen_build_id": None, "filed_at": None, "filed_office": None,
    "filed_receiver": None, "filed_sha256": None, "filed_fingerprint": None, "filed_note": None,
    "site_title": "Referendum Petition", "site_eyebrow": None, "volunteer_form_url": None,
    "site_description": "Where to sign, whether you are registered, and who to call — the Pittsburg County referendum petition on the proposed data center tax abatement. Volunteers of all kinds are needed.",
}


class Settings:
    def __init__(self, db: Session, petition: cfg.Petition | None = None):
        self.db = db
        self.p = petition or cfg.load()
        self._rows = {s.key: s.value for s in db.scalars(select(Setting)).all()}

    def raw(self, key: str) -> str | None:
        v = self._rows.get(key)
        if v not in (None, ""):
            return v
        d = DEFAULTS.get(key)
        if d is not None:
            return d
        # config-derived defaults
        p = self.p
        return {
            "adoption_date": p.measure.adoption_date.isoformat() if p.measure.adoption_date else None,
            "election_date": p.election.date.isoformat() if p.election.date else None,
            "registered_voters": str(p.threshold.registered_voters) if p.threshold.registered_voters else None,
            "registered_voters_source": p.threshold.registered_voters_source,
            "registered_voters_date": p.threshold.registered_voters_date.isoformat() if p.threshold.registered_voters_date else None,
            "sheets_per_pamphlet": str(p.layout.sheets_per_pamphlet), "rows_per_sheet": str(p.layout.rows_per_sheet),
            "overcollect_fraction": str(round(p.threshold.target_fraction / p.threshold.legal_fraction - 1, 4)),
            "captain_name": (p.contacts.get("petition_captain") or {}).get("name"),
            "captain_phone": (p.contacts.get("petition_captain") or {}).get("phone"),
            "site_eyebrow": f"{p.county} County, {p.state}",
        }.get(key)

    def set(self, key: str, value) -> None:
        if isinstance(value, date): value = value.isoformat()
        if isinstance(value, bool): value = "true" if value else "false"
        row = self.db.get(Setting, key)
        if row is None:
            row = Setting(key=key); self.db.add(row)
        row.value = None if value in (None, "") else str(value)
        self._rows[key] = row.value

    # typed accessors
    def date(self, key) -> date | None:
        v = self.raw(key); return date.fromisoformat(v) if v else None
    def int(self, key) -> int | None:
        v = self.raw(key); return int(float(v)) if v not in (None, "") else None
    def float(self, key) -> float | None:
        v = self.raw(key); return float(v) if v not in (None, "") else None
    def bool(self, key) -> bool:
        return str(self.raw(key)).lower() in ("true", "1", "yes", "on")

    @property
    def adoption_date(self): return self.date("adoption_date")
    @property
    def election_date(self): return self.date("election_date")
    @property
    def filing_deadline(self) -> date | None:
        o = self.date("filing_deadline_override")
        if o: return o
        a = self.adoption_date
        return a + timedelta(days=self.p.deadlines.filing_days_after_adoption) if a else None
    @property
    def registered_voters(self): return self.int("registered_voters")
    @property
    def legal_minimum(self) -> int | None:
        rv = self.registered_voters
        return ceil(rv * self.p.threshold.legal_fraction) if rv else None
    @property
    def target_signatures(self) -> int | None:
        lm = self.legal_minimum
        over = self.float("overcollect_fraction") or 0.5
        return ceil(lm * (1 + over)) if lm else None
    @property
    def est_valid_rate(self) -> float: return self.float("est_valid_rate") or 0.85
    @property
    def sheets_per_pamphlet(self) -> int: return self.int("sheets_per_pamphlet") or self.p.layout.sheets_per_pamphlet
    @property
    def rows_per_sheet(self) -> int: return self.int("rows_per_sheet") or self.p.layout.rows_per_sheet
    @property
    def print_run(self) -> int: return self.int("print_run") or 200
    @property
    def days_remaining(self) -> int | None:
        d = self.filing_deadline
        return (d - date.today()).days if d else None
