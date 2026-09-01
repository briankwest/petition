"""Live signature statistics — one function used by the public site, the admin
dashboard and the XLSX export so every number agrees."""
from __future__ import annotations
from collections import Counter
from datetime import date
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from .models import Pamphlet, Sheet, Issue, Circulator
from .settings import Settings


def signature_stats(db: Session, s: Settings) -> dict:
    coll, q, rej = db.execute(select(func.coalesce(func.sum(Sheet.collected), 0),
                                     func.coalesce(func.sum(Sheet.questionable), 0),
                                     func.coalesce(func.sum(Sheet.rejected), 0))).one()
    coll, q, rej = int(coll), int(q), int(rej)
    valid_est = max(coll - q - rej, 0)
    est_valid = round(valid_est * s.est_valid_rate)
    pam = Counter(db.scalars(select(Pamphlet.status)).all())
    sh = Counter(db.scalars(select(Sheet.status)).all())
    # content-free rows (template lines from the old tracker) are not issues
    open_issues = db.scalar(select(func.count()).select_from(Issue).where(
        Issue.status.in_(["Open", "Investigating", "Escalated"]),
        (Issue.issue_type.is_not(None)) | (Issue.notes.is_not(None)) | (Issue.pamphlet_id.is_not(None)) | (Issue.sheet_id.is_not(None)))) or 0
    circulators_ready = db.scalar(select(func.count()).select_from(Circulator).where(
        Circulator.active.is_(True), Circulator.registered_voter_verified.is_(True), Circulator.trained_on.is_not(None))) or 0
    legal_min, target = s.legal_minimum, s.target_signatures
    capacity = s.print_run * s.sheets_per_pamphlet * s.rows_per_sheet
    remaining = max(target - valid_est, 0) if target else None
    days = s.days_remaining
    return {
        "as_of": date.today().isoformat(),
        "collected": coll, "questionable": q, "rejected": rej, "valid_estimate": valid_est, "est_valid": est_valid,
        "est_valid_rate": s.est_valid_rate,
        "registered_voters": s.registered_voters, "legal_minimum": legal_min, "target": target,
        "remaining_to_target": remaining,
        "progress_to_legal": (valid_est / legal_min) if legal_min else None,
        "progress_to_target": (valid_est / target) if target else None,
        "capacity": capacity, "capacity_used": (coll / capacity) if capacity else None,
        "pamphlets": {k: pam.get(k, 0) for k in ["Ready to Print", "Printed", "Issued", "In Field", "Returned", "Audited", "Rejected", "Filed"]},
        "pamphlets_total": sum(pam.values()),
        "sheets": {k: sh.get(k, 0) for k in ["Blank", "In Field", "Returned", "Notarized", "Audited OK", "Needs Fix", "Rejected", "Filed"]},
        "open_issues": int(open_issues), "circulators_ready": int(circulators_ready),
        "adoption_date": s.adoption_date.isoformat() if s.adoption_date else None,
        "filing_deadline": s.filing_deadline.isoformat() if s.filing_deadline else None,
        "days_remaining": days,
        "signatures_per_day_needed": (round(remaining / days, 1) if (remaining and days and days > 0) else None),
    }
