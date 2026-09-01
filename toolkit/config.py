"""Load config/petition.yaml into a typed object with statute-derived fields.

Everything downstream (documents, workbook, map, site) reads from here so a date or a
count changes in exactly one place. `null` values are placeholders; `is_final_ready`
is False while any remain, and the formatted accessors render an explicit
"[… — TBD]" marker so a placeholder can never print as a blank.
"""
from __future__ import annotations
import math, os, re
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any
import yaml
from . import ROOT

DEFAULT_PATH = ROOT / "config" / "petition.yaml"
# Any of these in rendered text means the document is not ready to file.
PLACEHOLDER_RE = re.compile(r"\[(?:INSERT|PLACEHOLDER|TBD|NAME|PHONE|ADOPTION|DEADLINE|ELECTION|RESOLUTION|REGISTERED|LEGAL|TARGET|TITLE|EXACT)[^\]]*\]|\bTBD\b|\bDRAFT WORKING COPY\b")


def fmt_date(d: date | None, placeholder: str) -> str:
    return d.strftime("%B %-d, %Y") if d else placeholder


def _date(v) -> date | None:
    if v is None or v == "":
        return None
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v))


@dataclass
class Addressee:
    name: str
    title: str


@dataclass
class Measure:
    resolution_number: str | None
    title: str | None
    adoption_date: date | None
    short_description: str
    project_name: str
    districts: str
    abatement_percent: int
    exact_text_file: str

    @property
    def exact_text(self) -> str:
        p = ROOT / self.exact_text_file
        return p.read_text(encoding="utf-8").strip() if p.exists() else "[PLACEHOLDER — EXACT ADOPTED MEASURE]"

    @property
    def exact_text_is_placeholder(self) -> bool:
        return bool(PLACEHOLDER_RE.search(self.exact_text)) or not self.exact_text


@dataclass
class Election:
    date: date | None
    type: str = "regular"


@dataclass
class Deadlines:
    filing_days_after_adoption: int = 30
    protest_days_after_publication: int = 10
    ballot_title_da_review_days: int = 3
    ballot_title_appeal_days: int = 10


@dataclass
class Threshold:
    registered_voters: int | None
    registered_voters_source: str | None
    registered_voters_date: date | None
    legal_fraction: float = 0.10
    target_fraction: float = 0.15
    registered_voters_active: int | None = None
    registered_voters_inactive: int | None = None


@dataclass
class Layout:
    page: str = "legal"
    rows_per_sheet: int = 10
    sheets_per_pamphlet: int = 5
    body_pt: int = 12
    warning_pt: int = 12
    row_height_in: float = 0.5
    margins_in: float = 0.75
    duplex: str = "long-edge"


class Fmt:
    """Human-readable strings with explicit placeholder markers."""
    def __init__(self, p: "Petition"):
        self._p = p

    @property
    def adoption_date(self): return fmt_date(self._p.measure.adoption_date, "[ADOPTION DATE — TBD]")
    @property
    def filing_deadline(self): return fmt_date(self._p.filing_deadline, "[FILING DEADLINE — 30 days after adoption — TBD]")
    @property
    def election_date(self): return fmt_date(self._p.election.date, "[ELECTION DATE — TBD]")
    @property
    def resolution_number(self): return self._p.measure.resolution_number or "[INSERT EXACT RESOLUTION NUMBER AFTER ADOPTION]"
    @property
    def resolution_title(self): return self._p.measure.title or "[INSERT EXACT TITLE AS ADOPTED]"
    @property
    def registered_voters(self):
        v = self._p.threshold.registered_voters
        return f"{v:,}" if v else "[REGISTERED VOTER COUNT — TBD]"
    @property
    def legal_minimum(self):
        v = self._p.legal_minimum
        return f"{v:,}" if v else "[LEGAL MINIMUM — 10% of registered voters — TBD]"
    @property
    def target_signatures(self):
        v = self._p.target_signatures
        return f"{v:,}" if v else "[TARGET — TBD]"
    @property
    def abatement(self): return f"{self._p.measure.abatement_percent}%"


@dataclass
class Petition:
    county: str
    state: str
    governing_body: str
    addressee: Addressee
    measure: Measure
    election: Election
    deadlines: Deadlines
    threshold: Threshold
    gist: str
    ballot_title: str
    proponents: list[dict]
    layout: Layout
    contacts: dict
    links: dict
    site: dict
    statutes: list[str]
    raw: dict = field(default_factory=dict, repr=False)

    # ---- derived (statutory) ----
    @property
    def filing_deadline(self) -> date | None:
        """62 O.S. § 868(B)(3): signed copies within 30 days after adoption."""
        a = self.measure.adoption_date
        return a + timedelta(days=self.deadlines.filing_days_after_adoption) if a else None

    @property
    def legal_minimum(self) -> int | None:
        """62 O.S. § 868(B)(2): at least 10% of registered voters residing in the county."""
        rv = self.threshold.registered_voters
        return math.ceil(rv * self.threshold.legal_fraction) if rv else None

    @property
    def target_signatures(self) -> int | None:
        rv = self.threshold.registered_voters
        return math.ceil(rv * self.threshold.target_fraction) if rv else None

    @property
    def signatures_per_pamphlet(self) -> int:
        return self.layout.rows_per_sheet * self.layout.sheets_per_pamphlet

    @property
    def ballot_title_word_count(self) -> int:
        return len(self.ballot_title.split())

    @property
    def placeholders(self) -> list[str]:
        missing = []
        if not self.measure.resolution_number: missing.append("measure.resolution_number")
        if not self.measure.title: missing.append("measure.title")
        if not self.measure.adoption_date: missing.append("measure.adoption_date (tabled — no date yet)")
        if self.measure.exact_text_is_placeholder: missing.append(f"{self.measure.exact_text_file} (exact adopted text)")
        if not self.election.date: missing.append("election.date")
        if not self.threshold.registered_voters: missing.append("threshold.registered_voters")
        if not self.proponents: missing.append("proponents (1–3 of record)")
        for who in ("petition_captain",):
            c = self.contacts.get(who) or {}
            if not c.get("name") or not c.get("phone"): missing.append(f"contacts.{who}")
        return missing

    @property
    def is_final_ready(self) -> bool:
        return not self.placeholders

    @property
    def fmt(self) -> Fmt:
        return Fmt(self)

    @property
    def canonical_host(self) -> str:
        return (self.site or {}).get("canonical_host", "petition.mcalester.net")


def load(path: str | os.PathLike | None = None) -> Petition:
    path = Path(path or os.environ.get("PETITION_CONFIG") or DEFAULT_PATH)
    raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    m, e, t, l = raw["measure"], raw.get("election") or {}, raw["threshold"], raw.get("layout") or {}
    return Petition(
        county=raw["county"], state=raw["state"], governing_body=raw["governing_body"],
        addressee=Addressee(**raw["addressee"]),
        measure=Measure(
            resolution_number=m.get("resolution_number") or None, title=m.get("title") or None,
            adoption_date=_date(m.get("adoption_date")), short_description=" ".join(m["short_description"].split()),
            project_name=m["project_name"], districts=m["districts"], abatement_percent=int(m.get("abatement_percent", 85)),
            exact_text_file=m.get("exact_text_file", "measure/adopted-resolution.md"),
        ),
        election=Election(date=_date(e.get("date")), type=e.get("type", "regular")),
        deadlines=Deadlines(**(raw.get("deadlines") or {})),
        threshold=Threshold(
            registered_voters=int(t["registered_voters"]) if t.get("registered_voters") else None,
            registered_voters_source=t.get("registered_voters_source"),
            registered_voters_date=_date(t.get("registered_voters_date")),
            legal_fraction=float(t.get("legal_fraction", 0.10)), target_fraction=float(t.get("target_fraction", 0.15)),
            registered_voters_active=int(t["registered_voters_active"]) if t.get("registered_voters_active") else None,
            registered_voters_inactive=int(t["registered_voters_inactive"]) if t.get("registered_voters_inactive") else None,
        ),
        gist=" ".join(raw["gist"].split()), ballot_title=" ".join(raw["ballot_title"].split()),
        proponents=list(raw.get("proponents") or []),
        layout=Layout(**l), contacts=raw.get("contacts") or {}, links=raw.get("links") or {},
        site=raw.get("site") or {}, statutes=list(raw.get("statutes") or []), raw=raw,
    )
