"""Petition Master data model — the system of record for the Petition Captain.

Deliberately stores NO signer personal data: tracking is at pamphlet / sheet level
(counts, status, notary facts, defect codes). Signer names, addresses and birth dates
exist only on the paper pamphlets and, if the audit team keeps a line-level log, in a
file that never touches this database or the website.

Status vocabularies mirror the existing "Petition Captain Master Tracker.xlsx" so the
captain is not retrained; defect codes E1–E8 mirror 34 O.S. § 6.1(A)(1)–(8)."""
from __future__ import annotations
from datetime import date, datetime, time, timezone
from sqlalchemy import (String, Integer, Float, Boolean, Date, Time, DateTime, Text, ForeignKey, UniqueConstraint, LargeBinary)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base

PAMPHLET_STATUSES = ["Ready to Print", "Printed", "Issued", "In Field", "Returned", "Audited", "Rejected", "Filed"]
SHEET_STATUSES = ["Blank", "In Field", "Returned", "Notarized", "Audited OK", "Needs Fix", "Rejected", "Filed"]
VOLUNTEER_ROLES = ["Petition Captain", "Circulator", "Notary", "Verifier", "Event Lead", "Data Entry", "Runner", "Backup"]
ISSUE_STATUSES = ["Open", "Investigating", "Fixed", "Rejected Sheet", "Escalated", "Closed"]
ISSUE_PRIORITIES = ["Low", "Normal", "High", "Critical"]
QA_STATUSES = ["Not Started", "In Progress", "Done", "Blocked"]
LOCATION_STATUSES = ["planned", "active", "closed"]
# 34 O.S. § 6.1(A) — codes used on sheets and issues. Text comes from toolkit.statutes.exclusions().
DEFECT_CODES = ["E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8"]
SIGNUP_ROLES = ["Circulator", "Notary", "Event helper", "Driver", "Data entry", "Other"]
SIGNUP_STATUSES = ["New", "Approved", "Declined", "Archived"]
# website sign-up role -> Circulator.role vocabulary
SIGNUP_ROLE_MAP = {"Circulator": "Circulator", "Notary": "Notary", "Event helper": "Backup", "Driver": "Runner",
                   "Data entry": "Data Entry", "Other": "Backup"}
ISSUE_TYPES = DEFECT_CODES + ["Missing field", "Illegible", "Damaged pamphlet", "Detached page", "Other"]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Setting(Base):
    """Key/value site + campaign settings editable in admin (seeded from config/petition.yaml).
    Keys: adoption_date, election_date, filing_deadline_override, registered_voters,
    registered_voters_source, registered_voters_date, print_run, sheets_per_pamphlet,
    rows_per_sheet, est_valid_rate, overcollect_fraction, banner, public_show_counts,
    public_show_progress, captain_phone, captain_name, site_status."""
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(16), default="admin")   # admin | editor
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Circulator(Base):
    """Volunteers of every role; a circulator may only be issued a pamphlet once
    registered_voter_verified is True (34 O.S. § 6)."""
    __tablename__ = "circulators"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(32), default="Circulator")
    phone: Mapped[str | None] = mapped_column(String(32))
    email: Mapped[str | None] = mapped_column(String(120))
    registered_voter_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    registered_verified_on: Mapped[date | None] = mapped_column(Date)
    registered_verified_by: Mapped[str | None] = mapped_column(String(120))
    trained_on: Mapped[date | None] = mapped_column(Date)
    is_notary: Mapped[bool] = mapped_column(Boolean, default=False)
    compensated: Mapped[bool] = mapped_column(Boolean, default=False)
    availability: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    pamphlets: Mapped[list["Pamphlet"]] = relationship(back_populates="issued_to")

    @property
    def can_circulate(self) -> bool:
        return self.active and self.registered_voter_verified and self.trained_on is not None


class Pamphlet(Base):
    __tablename__ = "pamphlets"
    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(16), unique=True)          # "P-001"
    status: Mapped[str] = mapped_column(String(24), default="Ready to Print")
    print_batch: Mapped[str | None] = mapped_column(String(32))
    version_hash: Mapped[str | None] = mapped_column(String(64))            # must equal the filed pamphlet hash
    printed_on: Mapped[date | None] = mapped_column(Date)
    issued_to_id: Mapped[int | None] = mapped_column(ForeignKey("circulators.id"))
    issued_on: Mapped[date | None] = mapped_column(Date)
    returned_on: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    issued_to: Mapped[Circulator | None] = relationship(back_populates="pamphlets")
    sheets: Mapped[list["Sheet"]] = relationship(back_populates="pamphlet", cascade="all, delete-orphan",
                                                 order_by="Sheet.sheet_no")

    @property
    def collected(self) -> int: return sum(s.collected for s in self.sheets)
    @property
    def valid_estimate(self) -> int: return sum(s.valid_estimate for s in self.sheets)
    @property
    def notarized_sheets(self) -> int: return sum(1 for s in self.sheets if s.status in ("Notarized", "Audited OK", "Filed"))
    @property
    def audited_ok_sheets(self) -> int: return sum(1 for s in self.sheets if s.status in ("Audited OK", "Filed"))
    @property
    def rejected_sheets(self) -> int: return sum(1 for s in self.sheets if s.status == "Rejected")
    @property
    def filed(self) -> bool: return self.status == "Filed"


class Sheet(Base):
    """One signature sheet + its affidavit. Counts only — never signer data."""
    __tablename__ = "sheets"
    __table_args__ = (UniqueConstraint("pamphlet_id", "sheet_no"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    pamphlet_id: Mapped[int] = mapped_column(ForeignKey("pamphlets.id", ondelete="CASCADE"))
    sheet_no: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24), default="Blank")
    circulator_id: Mapped[int | None] = mapped_column(ForeignKey("circulators.id"))
    issued_on: Mapped[date | None] = mapped_column(Date)
    returned_on: Mapped[date | None] = mapped_column(Date)
    collected: Mapped[int] = mapped_column(Integer, default=0)
    questionable: Mapped[int] = mapped_column(Integer, default=0)
    rejected: Mapped[int] = mapped_column(Integer, default=0)
    notarized_on: Mapped[date | None] = mapped_column(Date)
    notary_name: Mapped[str | None] = mapped_column(String(120))
    notary_commission: Mapped[str | None] = mapped_column(String(32))
    notary_expiration: Mapped[date | None] = mapped_column(Date)
    defect_codes: Mapped[str | None] = mapped_column(String(64))            # "E1,E7"
    notes: Mapped[str | None] = mapped_column(Text)
    pamphlet: Mapped[Pamphlet] = relationship(back_populates="sheets")
    circulator: Mapped[Circulator | None] = relationship()

    @property
    def sheet_id(self) -> str: return f"{self.pamphlet.number}-S{self.sheet_no}"
    @property
    def valid_estimate(self) -> int: return max(self.collected - self.questionable - self.rejected, 0)
    @property
    def defects(self) -> list[str]: return [c for c in (self.defect_codes or "").split(",") if c]


class Issue(Base):
    __tablename__ = "issues"
    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(16), unique=True)           # "I-001"
    opened_on: Mapped[date | None] = mapped_column(Date)
    pamphlet_id: Mapped[int | None] = mapped_column(ForeignKey("pamphlets.id"))
    sheet_id: Mapped[int | None] = mapped_column(ForeignKey("sheets.id"))
    issue_type: Mapped[str | None] = mapped_column(String(32))            # E1..E8 or ISSUE_TYPES
    status: Mapped[str] = mapped_column(String(24), default="Open")
    priority: Mapped[str] = mapped_column(String(16), default="Normal")
    notes: Mapped[str | None] = mapped_column(Text)
    pamphlet: Mapped[Pamphlet | None] = relationship()
    sheet: Mapped[Sheet | None] = relationship()


class Location(Base):
    """A place where an official pamphlet can be signed. Public when `public` is True."""
    __tablename__ = "locations"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    address: Mapped[str | None] = mapped_column(String(200))
    city: Mapped[str | None] = mapped_column(String(80))
    zip: Mapped[str | None] = mapped_column(String(10))
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    precinct: Mapped[str | None] = mapped_column(String(8))                # derived by point-in-polygon
    status: Mapped[str] = mapped_column(String(16), default="planned")
    hours: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)
    public: Mapped[bool] = mapped_column(Boolean, default=True)
    events: Mapped[list["Event"]] = relationship(back_populates="location", cascade="all, delete-orphan")


class Event(Base):
    """A dated signing shift at a location."""
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id", ondelete="CASCADE"))
    date: Mapped[date | None] = mapped_column(Date)
    start: Mapped[time | None] = mapped_column(Time)
    end: Mapped[time | None] = mapped_column(Time)
    lead_id: Mapped[int | None] = mapped_column(ForeignKey("circulators.id"))
    volunteers_needed: Mapped[int | None] = mapped_column(Integer)
    pamphlets_issued: Mapped[int | None] = mapped_column(Integer)
    expected_signatures: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
    public: Mapped[bool] = mapped_column(Boolean, default=True)
    location: Mapped[Location] = relationship(back_populates="events")
    lead: Mapped[Circulator | None] = relationship()


class Contact(Base):
    __tablename__ = "contacts"
    id: Mapped[int] = mapped_column(primary_key=True)
    role: Mapped[str] = mapped_column(String(120))
    name: Mapped[str | None] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(32))
    email: Mapped[str | None] = mapped_column(String(120))
    address: Mapped[str | None] = mapped_column(String(200))
    hours: Mapped[str | None] = mapped_column(String(120))
    public: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=100)


class QATask(Base):
    """Filing QA checklist (from the tracker's 'Filing QA' sheet / the Action Plan)."""
    __tablename__ = "qa_tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    task: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="Not Started")
    owner: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=100)


class RecordsLog(Base):
    """Filing & Records Log — every office visit, filing, print batch, handoff (Action Plan §11)."""
    __tablename__ = "records_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    item: Mapped[str] = mapped_column(String(200))
    office: Mapped[str | None] = mapped_column(String(160))
    person: Mapped[str | None] = mapped_column(String(120))
    documents: Mapped[str | None] = mapped_column(Text)
    receipt_obtained: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class VolunteerSignup(Base):
    """A volunteer sign-up submitted on the public site, waiting for the captain's review.
    Approving one creates a Circulator record (registration + training are still verified
    by the captain before any pamphlet is issued — 34 O.S. § 6)."""
    __tablename__ = "volunteer_signups"
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(32))
    email: Mapped[str | None] = mapped_column(String(120))
    city: Mapped[str | None] = mapped_column(String(80))
    zip: Mapped[str | None] = mapped_column(String(10))
    roles: Mapped[str | None] = mapped_column(String(120))                 # comma-separated SIGNUP_ROLES
    says_registered_voter: Mapped[bool] = mapped_column(Boolean, default=False)   # self-reported, unverified
    says_18: Mapped[bool] = mapped_column(Boolean, default=False)
    availability: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="New")
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[str | None] = mapped_column(String(64))
    circulator_id: Mapped[int | None] = mapped_column(ForeignKey("circulators.id"))
    ip: Mapped[str | None] = mapped_column(String(64))
    circulator: Mapped[Circulator | None] = relationship()

    @property
    def role_list(self) -> list[str]:
        return [r for r in (self.roles or "").split(",") if r]


class DocumentBuild(Base):
    """One server-side document generation run (stored in Postgres so it survives deploys)."""
    __tablename__ = "document_builds"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(8))                      # draft | final
    status: Mapped[str] = mapped_column(String(8), default="running") # running | ok | failed
    built_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    built_by: Mapped[str | None] = mapped_column(String(64))
    duplex: Mapped[str | None] = mapped_column(String(16))
    manifest: Mapped[str | None] = mapped_column(Text)                # JSON
    check_report: Mapped[str | None] = mapped_column(Text)            # JSON [{doc,check,ok,detail}]
    petition_snapshot: Mapped[str | None] = mapped_column(Text)       # JSON summary + placeholders
    error: Mapped[str | None] = mapped_column(Text)
    filed: Mapped[bool] = mapped_column(Boolean, default=False)
    pamphlet_sha256: Mapped[str | None] = mapped_column(String(64))
    pamphlet_fingerprint: Mapped[str | None] = mapped_column(String(64))
    files: Mapped[list["DocumentFile"]] = relationship(back_populates="build", cascade="all, delete-orphan", order_by="DocumentFile.name")

    @property
    def checks_failed(self) -> int:
        import json as _j
        try:
            return sum(1 for r in _j.loads(self.check_report or "[]") if not r.get("ok"))
        except ValueError:
            return 0


class DocumentFile(Base):
    __tablename__ = "document_files"
    id: Mapped[int] = mapped_column(primary_key=True)
    build_id: Mapped[int] = mapped_column(ForeignKey("document_builds.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(80))
    pages: Mapped[int | None] = mapped_column(Integer)
    bytes_len: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str | None] = mapped_column(String(64))
    content: Mapped[bytes] = mapped_column(LargeBinary)
    build: Mapped[DocumentBuild] = relationship(back_populates="files")


class PetitionAttachment(Base):
    """Adopted-resolution / exhibit PDFs uploaded on /admin/petition. Reproduced page-by-page
    inside the pamphlet after the typed measure text (each page scaled to legal and centered),
    so text + exhibits together form the exact copy of the measure (34 O.S. § 1)."""
    __tablename__ = "petition_attachments"
    id: Mapped[int] = mapped_column(primary_key=True)
    position: Mapped[int] = mapped_column(Integer, default=100)
    name: Mapped[str] = mapped_column(String(120))
    content: Mapped[bytes] = mapped_column(LargeBinary)
    pages: Mapped[int | None] = mapped_column(Integer)
    bytes_len: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str | None] = mapped_column(String(64))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    uploaded_by: Mapped[str | None] = mapped_column(String(64))
