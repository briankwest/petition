"""Petition Captain admin: the system of record for pamphlets, sheets, circulators, issues,
events, contacts, settings. Server-rendered forms; CSRF on every POST; login required."""
from __future__ import annotations
import io
from datetime import date, datetime, timezone
from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy import select, func, desc
from sqlalchemy.orm import Session, selectinload
from ..db import get_db
from .. import models as m
from ..settings import Settings, DEFAULTS
from ..stats import signature_stats
from ..auth import (current_user, require_user, require_admin, hash_password, verify_password,
                    read_session, write_session, clear_session)
from .. import forms as F
from . import render
from toolkit import statutes

router = APIRouter(prefix="/admin")
AUTH = [Depends(require_user)]


def go(url: str, msg: str | None = None, err: str | None = None) -> RedirectResponse:
    if msg:
        url += ("&" if "?" in url else "?") + "msg=" + quote(msg)
    if err:
        url += ("&" if "?" in url else "?") + "err=" + quote(err)
    return RedirectResponse(url, status_code=303)


def field(name, label, type="text", value=None, options=None, help=None, required=False, step=None, rows=3):
    if isinstance(value, bool):
        value = value
    elif value is not None and not isinstance(value, str):
        value = value.isoformat() if hasattr(value, "isoformat") else str(value)
    return {"name": name, "label": label, "type": type, "value": value, "options": options or [], "help": help,
            "required": required, "step": step, "rows": rows}


# ---------- auth ----------
@router.get("/login")
def login_form(request: Request, next: str = "/admin", user=Depends(current_user)):
    if user:
        return go("/admin")
    return render(request, "admin/login.html", next=next)


@router.post("/login")
async def login(request: Request, db: Session = Depends(get_db)):
    form = await F.parse(request)
    username, password, nxt = F.s(form, "username", ""), F.s(form, "password", ""), F.s(form, "next", "/admin")
    user = db.scalar(select(m.User).where(m.User.username == username))
    if not user or not user.active or not verify_password(password, user.password_hash):
        return render(request, "admin/login.html", next=nxt, err="Wrong username or password.", status_code=401)
    sess = read_session(request)
    sess["uid"] = user.id
    sess["_dirty"] = True
    if not nxt.startswith("/"):
        nxt = "/admin"
    resp = RedirectResponse(nxt, status_code=303)
    write_session(request, resp)
    return resp


@router.post("/logout")
async def logout(request: Request):
    await F.parse(request)
    resp = RedirectResponse("/admin/login", status_code=303)
    clear_session(request, resp)
    return resp


# ---------- dashboard ----------
@router.get("", dependencies=AUTH)
@router.get("/", dependencies=AUTH)
def dashboard(request: Request, db: Session = Depends(get_db)):
    s = Settings(db)
    st = signature_stats(db, s)
    issues = db.scalars(select(m.Issue).where(m.Issue.status.in_(["Open", "Investigating", "Escalated"]))
                        .order_by(desc(m.Issue.priority == "Critical"), m.Issue.number).limit(10)).all()
    out = db.scalars(select(m.Pamphlet).options(selectinload(m.Pamphlet.issued_to)).where(m.Pamphlet.status.in_(["Issued", "In Field"]))
                     .order_by(m.Pamphlet.issued_on).limit(15)).all()
    signups_new = db.scalar(select(func.count()).select_from(m.VolunteerSignup).where(m.VolunteerSignup.status == "New")) or 0
    return render(request, "admin/dashboard.html", s=s, st=st, issues=issues, outstanding=out, signups_new=signups_new)


# ---------- settings ----------
SETTING_FIELDS = [
    ("site_title", "Site title (top of every page)", "text", "Shown in the header and the browser tab. Change it to reuse this site for another petition."),
    ("site_eyebrow", "Site eyebrow (small line above the title)", "text", None),
    ("adoption_date", "Resolution adoption date", "date", "Leave blank while the resolution is tabled. Sets the 30-day filing clock (62 O.S. § 868(B)(3))."),
    ("filing_deadline_override", "Filing deadline override", "date", "Only if the Election Board gives a different date in writing."),
    ("election_date", "Election date", "date", "Next general county election after filing (62 O.S. § 868(H)) — confirm with the Election Board."),
    ("registered_voters", "Registered voters in county", "number", "Written, dated figure from the County Election Board. Legal minimum = 10%."),
    ("registered_voters_source", "Voter count source", "text", "Who gave it and how (email, letter)."),
    ("registered_voters_date", "Voter count date", "date", None),
    ("print_run", "Print run (pamphlets)", "number", None),
    ("sheets_per_pamphlet", "Signature sheets per pamphlet", "number", None),
    ("rows_per_sheet", "Signature lines per sheet", "number", None),
    ("est_valid_rate", "Estimated validity rate", "number", "Fraction of collected signatures expected to survive verification (e.g. 0.85)."),
    ("overcollect_fraction", "Overcollection fraction", "number", "Target = legal minimum × (1 + this). 0.5 = collect 150% of the minimum."),
    ("site_status", "Site status", "select", None),
    ("banner", "Public banner", "textarea", "Shown at the top of every public page."),
    ("public_show_counts", "Show live counts publicly", "checkbox", None),
    ("public_show_progress", "Show progress bar publicly", "checkbox", None),
    ("captain_name", "Petition Captain name", "text", None),
    ("captain_phone", "Petition Captain phone", "text", None),
    ("volunteer_form_url", "External volunteer form URL (optional)", "text", "Leave blank to use the built-in sign-up form, which feeds the Sign-ups queue for your approval."),
]
SITE_STATUSES = ["pre-adoption", "filed-not-circulating", "circulating", "submitted", "closed"]


@router.get("/settings", dependencies=AUTH)
def settings_form(request: Request, db: Session = Depends(get_db)):
    s = Settings(db)
    fields = []
    th = s.p.threshold
    for key, label, typ, help in SETTING_FIELDS:
        val = s.raw(key)
        if typ == "checkbox":
            val = s.bool(key)
        fd = field(key, label, typ, val, options=SITE_STATUSES if key == "site_status" else None, help=help,
                   step="any" if typ == "number" else None)
        if key == "registered_voters":
            fd["help"] = ("62 O.S. § 868(B)(2) — 10% of registered voters; inactive voters are still registered, so we plan "
                          "against the total; confirm with the Election Board which figure they count against.")
            fd["readonly"] = [("Config value", f"{th.registered_voters:,}" if th.registered_voters else "—"),
                              ("Config source", th.registered_voters_source or "—"),
                              ("Config date", th.registered_voters_date.isoformat() if th.registered_voters_date else "—")]
        fields.append(fd)
    return render(request, "admin/settings.html", s=s, fields=fields, deadline=s.filing_deadline,
                  legal_min=s.legal_minimum, target=s.target_signatures)


@router.post("/settings", dependencies=AUTH)
async def settings_save(request: Request, db: Session = Depends(get_db)):
    form = await F.parse(request)
    s = Settings(db)
    for key, _, typ, _ in SETTING_FIELDS:
        if typ == "checkbox":
            s.set(key, F.b(form, key))
        elif typ == "date":
            v = F.s(form, key)
            if v and F.d(form, key) is None:
                return go("/admin/settings", err=f"{key}: use YYYY-MM-DD")
            s.set(key, v)
        else:
            s.set(key, F.s(form, key))
    db.commit()
    return go("/admin/settings", msg="Settings saved.")


# ---------- pamphlets ----------
@router.get("/pamphlets", dependencies=AUTH)
def pamphlets(request: Request, status: str = "", q: str = "", db: Session = Depends(get_db)):
    stmt = select(m.Pamphlet).options(selectinload(m.Pamphlet.sheets), selectinload(m.Pamphlet.issued_to))
    if status:
        stmt = stmt.where(m.Pamphlet.status == status)
    if q:
        stmt = stmt.where(m.Pamphlet.number.ilike(f"%{q}%"))
    rows = db.scalars(stmt.order_by(m.Pamphlet.number)).all()
    counts = dict(db.execute(select(m.Pamphlet.status, func.count()).group_by(m.Pamphlet.status)).all())
    circ = db.scalars(select(m.Circulator).where(m.Circulator.active.is_(True)).order_by(m.Circulator.name)).all()
    s = Settings(db)
    return render(request, "admin/pamphlets.html", rows=rows, status=status, q=q, counts=counts, statuses=m.PAMPHLET_STATUSES,
                  circulators=circ, s=s, next_number=_next_number(db, m.Pamphlet, "P-"))


def _next_number(db: Session, model, prefix: str) -> int:
    nums = db.scalars(select(model.number)).all()
    return max((int(n.split("-")[1]) for n in nums if n.startswith(prefix) and n.split("-")[1].isdigit()), default=0) + 1


@router.post("/pamphlets/bulk-create", dependencies=AUTH)
async def pamphlets_bulk(request: Request, db: Session = Depends(get_db)):
    form = await F.parse(request)
    s = Settings(db)
    start, count = F.i(form, "start", 1), F.i(form, "count", 0)
    sheets = F.i(form, "sheets", s.sheets_per_pamphlet)
    batch = F.s(form, "print_batch")
    if not count or count < 1 or count > 5000:
        return go("/admin/pamphlets", err="Enter how many pamphlets to create (1–5000).")
    existing = set(db.scalars(select(m.Pamphlet.number)).all())
    made = 0
    for n in range(start, start + count):
        num = f"P-{n:03d}"
        if num in existing:
            continue
        p = m.Pamphlet(number=num, print_batch=batch)
        p.sheets = [m.Sheet(sheet_no=i) for i in range(1, sheets + 1)]
        db.add(p)
        made += 1
    db.commit()
    return go("/admin/pamphlets", msg=f"Created {made} pamphlets ({sheets} sheets each); {count - made} already existed.")


def _pamphlet(db: Session, number: str) -> m.Pamphlet:
    p = db.scalar(select(m.Pamphlet).options(selectinload(m.Pamphlet.sheets).selectinload(m.Sheet.circulator),
                                             selectinload(m.Pamphlet.issued_to)).where(m.Pamphlet.number == number))
    if not p:
        raise HTTPException(404, "No such pamphlet")
    return p


@router.get("/pamphlets/{number}", dependencies=AUTH)
def pamphlet_detail(request: Request, number: str, db: Session = Depends(get_db)):
    p = _pamphlet(db, number)
    circ = db.scalars(select(m.Circulator).where(m.Circulator.active.is_(True)).order_by(m.Circulator.name)).all()
    issues = db.scalars(select(m.Issue).where(m.Issue.pamphlet_id == p.id).order_by(m.Issue.number)).all()
    return render(request, "admin/pamphlet.html", p=p, circulators=circ, statuses=m.PAMPHLET_STATUSES,
                  sheet_statuses=m.SHEET_STATUSES, defect_codes=m.DEFECT_CODES,
                  defect_text=dict(zip(m.DEFECT_CODES, statutes.exclusions())), issues=issues)


@router.post("/pamphlets/{number}", dependencies=AUTH)
async def pamphlet_save(request: Request, number: str, db: Session = Depends(get_db)):
    form = await F.parse(request)
    p = _pamphlet(db, number)
    p.status = F.s(form, "status", p.status)
    p.print_batch, p.version_hash, p.notes = F.s(form, "print_batch"), F.s(form, "version_hash"), F.s(form, "notes")
    p.printed_on, p.issued_on, p.returned_on = F.d(form, "printed_on"), F.d(form, "issued_on"), F.d(form, "returned_on")
    cid = F.i(form, "issued_to_id")
    if cid != (p.issued_to_id or None) and cid:
        c = db.get(m.Circulator, cid)
        if not c or not c.can_circulate:
            return go(f"/admin/pamphlets/{number}", err="That volunteer is not cleared to circulate: registered-voter verification and training must be recorded first (34 O.S. § 6).")
    p.issued_to_id = cid
    for sh in p.sheets:
        k = f"s{sh.sheet_no}_"
        sh.status = F.s(form, k + "status", sh.status)
        sh.circulator_id = F.i(form, k + "circulator_id")
        sh.collected = max(F.i(form, k + "collected", 0) or 0, 0)
        sh.questionable = max(F.i(form, k + "questionable", 0) or 0, 0)
        sh.rejected = max(F.i(form, k + "rejected", 0) or 0, 0)
        sh.issued_on, sh.returned_on, sh.notarized_on = F.d(form, k + "issued_on"), F.d(form, k + "returned_on"), F.d(form, k + "notarized_on")
        sh.notary_name, sh.notary_commission = F.s(form, k + "notary_name"), F.s(form, k + "notary_commission")
        sh.notary_expiration = F.d(form, k + "notary_expiration")
        sh.defect_codes = ",".join(c for c in F.lst(form, k + "defects") if c in m.DEFECT_CODES) or None
        sh.notes = F.s(form, k + "notes")
    db.commit()
    return go(f"/admin/pamphlets/{number}", msg="Pamphlet saved.")


@router.post("/pamphlets/{number}/issue", dependencies=AUTH)
async def pamphlet_issue(request: Request, number: str, db: Session = Depends(get_db)):
    form = await F.parse(request)
    p = _pamphlet(db, number)
    c = db.get(m.Circulator, F.i(form, "circulator_id") or 0)
    if not c:
        return go(f"/admin/pamphlets/{number}", err="Pick a circulator.")
    if not c.can_circulate:
        why = []
        if not c.registered_voter_verified: why.append("Oklahoma voter registration not verified")
        if c.trained_on is None: why.append("training not recorded")
        if not c.active: why.append("inactive")
        return go(f"/admin/pamphlets/{number}", err=f"Cannot issue to {c.name}: {', '.join(why)}. Circulators must be registered Oklahoma voters (34 O.S. § 6).")
    p.issued_to_id, p.issued_on, p.status = c.id, date.today(), "Issued"
    for sh in p.sheets:
        if sh.status == "Blank":
            sh.status, sh.circulator_id, sh.issued_on = "In Field", c.id, date.today()
    db.commit()
    return go(f"/admin/pamphlets/{number}", msg=f"Issued to {c.name}.")


@router.post("/pamphlets/{number}/return", dependencies=AUTH)
async def pamphlet_return(request: Request, number: str, db: Session = Depends(get_db)):
    await F.parse(request)
    p = _pamphlet(db, number)
    p.status, p.returned_on = "Returned", date.today()
    for sh in p.sheets:
        if sh.status == "In Field":
            sh.status, sh.returned_on = "Returned", date.today()
    db.commit()
    return go(f"/admin/pamphlets/{number}", msg="Marked returned. Enter sheet counts and notary details below.")


@router.post("/pamphlets/{number}/file", dependencies=AUTH)
async def pamphlet_file(request: Request, number: str, db: Session = Depends(get_db)):
    await F.parse(request)
    p = _pamphlet(db, number)
    p.status = "Filed"
    for sh in p.sheets:
        if sh.status in ("Notarized", "Audited OK"):
            sh.status = "Filed"
    db.commit()
    return go(f"/admin/pamphlets/{number}", msg="Marked filed with the Election Board.")


# ---------- circulators ----------
CIRC_FIELDS = lambda c=None: [
    field("name", "Name", value=getattr(c, "name", None), required=True),
    field("role", "Role", "select", getattr(c, "role", "Circulator"), options=m.VOLUNTEER_ROLES),
    field("phone", "Phone", value=getattr(c, "phone", None)),
    field("email", "Email", value=getattr(c, "email", None)),
    field("registered_voter_verified", "Oklahoma voter registration verified", "checkbox", getattr(c, "registered_voter_verified", False),
          help="Required before any pamphlet can be issued (34 O.S. § 6). Check the OK Voter Portal or the Election Board."),
    field("registered_verified_on", "Verified on", "date", getattr(c, "registered_verified_on", None)),
    field("registered_verified_by", "Verified by", value=getattr(c, "registered_verified_by", None)),
    field("trained_on", "Training completed on", "date", getattr(c, "trained_on", None)),
    field("is_notary", "Is a notary", "checkbox", getattr(c, "is_notary", False)),
    field("compensated", "Paid circulator", "checkbox", getattr(c, "compensated", False), help="If anyone is paid, tell counsel — a compensation disclosure may be needed."),
    field("availability", "Availability", "textarea", getattr(c, "availability", None), rows=2),
    field("notes", "Notes", "textarea", getattr(c, "notes", None)),
    field("active", "Active", "checkbox", getattr(c, "active", True)),
]


def _apply_circ(c: m.Circulator, form):
    c.name, c.role = F.s(form, "name", c.name or ""), F.s(form, "role", "Circulator")
    c.phone, c.email = F.s(form, "phone"), F.s(form, "email")
    c.registered_voter_verified = F.b(form, "registered_voter_verified")
    c.registered_verified_on, c.registered_verified_by = F.d(form, "registered_verified_on"), F.s(form, "registered_verified_by")
    c.trained_on, c.is_notary, c.compensated = F.d(form, "trained_on"), F.b(form, "is_notary"), F.b(form, "compensated")
    c.availability, c.notes, c.active = F.s(form, "availability"), F.s(form, "notes"), F.b(form, "active")


@router.get("/circulators", dependencies=AUTH)
def circulators(request: Request, q: str = "", show: str = "active", db: Session = Depends(get_db)):
    stmt = select(m.Circulator).options(selectinload(m.Circulator.pamphlets))
    if show == "active":
        stmt = stmt.where(m.Circulator.active.is_(True))
    if q:
        stmt = stmt.where(m.Circulator.name.ilike(f"%{q}%"))
    rows = db.scalars(stmt.order_by(m.Circulator.name)).all()
    signups_new = db.scalar(select(func.count()).select_from(m.VolunteerSignup).where(m.VolunteerSignup.status == "New")) or 0
    return render(request, "admin/circulators.html", rows=rows, q=q, show=show, signups_new=signups_new)


# ---------- volunteer sign-ups (from the public form) ----------
@router.get("/signups", dependencies=AUTH)
def signups(request: Request, status: str = "New", db: Session = Depends(get_db)):
    stmt = select(m.VolunteerSignup).options(selectinload(m.VolunteerSignup.circulator))
    if status != "all":
        stmt = stmt.where(m.VolunteerSignup.status == status)
    rows = db.scalars(stmt.order_by(desc(m.VolunteerSignup.created_at))).all()
    counts = {k: (db.scalar(select(func.count()).select_from(m.VolunteerSignup).where(m.VolunteerSignup.status == k)) or 0) for k in m.SIGNUP_STATUSES}
    return render(request, "admin/signups.html", rows=rows, status=status, counts=counts, statuses=m.SIGNUP_STATUSES)


def _signup(db: Session, sid: int) -> m.VolunteerSignup:
    return db.get(m.VolunteerSignup, sid) or _404()


@router.post("/signups/{sid}/approve", dependencies=AUTH)
async def signup_approve(request: Request, sid: int, db: Session = Depends(get_db)):
    await F.parse(request)
    su = _signup(db, sid)
    if su.circulator_id:
        return go(f"/admin/circulators/{su.circulator_id}", msg="Already approved.")
    roles = su.role_list or ["Circulator"]
    primary = "Circulator" if "Circulator" in roles else roles[0]
    c = m.Circulator(
        name=su.name, phone=su.phone, email=su.email, role=m.SIGNUP_ROLE_MAP.get(primary, "Backup"),
        is_notary="Notary" in roles, availability=su.availability,
        notes=(f"From website sign-up {su.created_at:%Y-%m-%d}. Roles: {', '.join(roles)}. "
               f"Self-reported registered Pittsburg County voter: {'yes' if su.says_registered_voter else 'no'}; "
               f"18 or older: {'yes' if su.says_18 else 'no'}." + (f"\n{su.notes}" if su.notes else "")),
    )
    db.add(c); db.flush()
    su.status, su.reviewed_at, su.reviewed_by, su.circulator_id = "Approved", datetime.now(timezone.utc), request.state.user.username, c.id
    db.commit()
    return go(f"/admin/circulators/{c.id}", msg=f"Approved {c.name}. Verify voter registration and record training before issuing a pamphlet (34 O.S. § 6).")


@router.post("/signups/{sid}/status", dependencies=AUTH)
async def signup_status(request: Request, sid: int, db: Session = Depends(get_db)):
    form = await F.parse(request)
    su = _signup(db, sid)
    st = F.s(form, "status")
    if st not in m.SIGNUP_STATUSES or st == "Approved":
        return go("/admin/signups", err="Invalid status.")
    su.status, su.reviewed_at, su.reviewed_by = st, datetime.now(timezone.utc), request.state.user.username
    db.commit()
    return go("/admin/signups", msg=f"{su.name}: {st.lower()}.")


@router.get("/circulators/new", dependencies=AUTH)
def circulator_new(request: Request):
    return render(request, "admin/form.html", title="New volunteer", fields=CIRC_FIELDS(), action="/admin/circulators/new", back="/admin/circulators")


@router.post("/circulators/new", dependencies=AUTH)
async def circulator_create(request: Request, db: Session = Depends(get_db)):
    form = await F.parse(request)
    if not F.s(form, "name"):
        return go("/admin/circulators/new", err="Name is required.")
    c = m.Circulator(name=F.s(form, "name"))
    _apply_circ(c, form)
    db.add(c); db.commit()
    return go("/admin/circulators", msg=f"Added {c.name}.")


@router.get("/circulators/{cid}", dependencies=AUTH)
def circulator_edit(request: Request, cid: int, db: Session = Depends(get_db)):
    c = db.get(m.Circulator, cid) or _404()
    return render(request, "admin/form.html", title=f"Volunteer: {c.name}", fields=CIRC_FIELDS(c), action=f"/admin/circulators/{cid}",
                  back="/admin/circulators", extra=render_pamphlet_list(c))


def render_pamphlet_list(c: m.Circulator) -> str:
    if not c.pamphlets:
        return ""
    items = "".join(f'<li><a href="/admin/pamphlets/{p.number}">{p.number}</a> — {p.status}</li>' for p in c.pamphlets)
    return f"<h3>Pamphlets</h3><ul>{items}</ul>"


@router.post("/circulators/{cid}", dependencies=AUTH)
async def circulator_save(request: Request, cid: int, db: Session = Depends(get_db)):
    form = await F.parse(request)
    c = db.get(m.Circulator, cid) or _404()
    _apply_circ(c, form); db.commit()
    return go("/admin/circulators", msg=f"Saved {c.name}.")


def _404():
    raise HTTPException(404)


# ---------- issues ----------
def ISSUE_FIELDS(db: Session, i=None):
    pams = [("", "—")] + [(str(p.id), p.number) for p in db.scalars(select(m.Pamphlet).order_by(m.Pamphlet.number)).all()]
    return [
        field("opened_on", "Date", "date", getattr(i, "opened_on", date.today())),
        field("pamphlet_id", "Pamphlet", "select", str(getattr(i, "pamphlet_id", "") or ""), options=pams),
        field("sheet_no", "Sheet #", "number", getattr(getattr(i, "sheet", None), "sheet_no", None)),
        field("issue_type", "Issue type", "select", getattr(i, "issue_type", "Other"),
              options=[(c, f"{c} — {t[:70]}") for c, t in zip(m.DEFECT_CODES, statutes.exclusions())] + [(x, x) for x in m.ISSUE_TYPES if x not in m.DEFECT_CODES]),
        field("status", "Status", "select", getattr(i, "status", "Open"), options=m.ISSUE_STATUSES),
        field("priority", "Priority", "select", getattr(i, "priority", "Normal"), options=m.ISSUE_PRIORITIES),
        field("notes", "Resolution / notes", "textarea", getattr(i, "notes", None)),
    ]


def _apply_issue(i: m.Issue, form, db: Session):
    i.opened_on, i.issue_type = F.d(form, "opened_on"), F.s(form, "issue_type")
    i.status, i.priority, i.notes = F.s(form, "status", "Open"), F.s(form, "priority", "Normal"), F.s(form, "notes")
    i.pamphlet_id = F.i(form, "pamphlet_id")
    i.sheet_id = None
    sn = F.i(form, "sheet_no")
    if i.pamphlet_id and sn:
        sh = db.scalar(select(m.Sheet).where(m.Sheet.pamphlet_id == i.pamphlet_id, m.Sheet.sheet_no == sn))
        i.sheet_id = sh.id if sh else None


@router.get("/issues", dependencies=AUTH)
def issues(request: Request, status: str = "open", db: Session = Depends(get_db)):
    stmt = select(m.Issue).options(selectinload(m.Issue.pamphlet), selectinload(m.Issue.sheet))
    if status == "open":
        stmt = stmt.where(m.Issue.status.in_(["Open", "Investigating", "Escalated"]))
    elif status and status != "all":
        stmt = stmt.where(m.Issue.status == status)
    rows = db.scalars(stmt.order_by(desc(m.Issue.number))).all()
    return render(request, "admin/issues.html", rows=rows, status=status, statuses=m.ISSUE_STATUSES)


@router.get("/issues/new", dependencies=AUTH)
def issue_new(request: Request, pamphlet: str = "", db: Session = Depends(get_db)):
    fields = ISSUE_FIELDS(db)
    if pamphlet:
        p = db.scalar(select(m.Pamphlet).where(m.Pamphlet.number == pamphlet))
        if p:
            fields[1]["value"] = str(p.id)
    return render(request, "admin/form.html", title="New issue", fields=fields, action="/admin/issues/new", back="/admin/issues")


@router.post("/issues/new", dependencies=AUTH)
async def issue_create(request: Request, db: Session = Depends(get_db)):
    form = await F.parse(request)
    i = m.Issue(number=f"I-{_next_number(db, m.Issue, 'I-'):03d}")
    _apply_issue(i, form, db)
    db.add(i); db.commit()
    return go("/admin/issues", msg=f"Opened {i.number}.")


@router.get("/issues/{iid}", dependencies=AUTH)
def issue_edit(request: Request, iid: int, db: Session = Depends(get_db)):
    i = db.get(m.Issue, iid) or _404()
    return render(request, "admin/form.html", title=f"Issue {i.number}", fields=ISSUE_FIELDS(db, i), action=f"/admin/issues/{iid}", back="/admin/issues")


@router.post("/issues/{iid}", dependencies=AUTH)
async def issue_save(request: Request, iid: int, db: Session = Depends(get_db)):
    form = await F.parse(request)
    i = db.get(m.Issue, iid) or _404()
    _apply_issue(i, form, db); db.commit()
    return go("/admin/issues", msg=f"Saved {i.number}.")


# ---------- locations & events ----------
LOC_FIELDS = lambda l=None: [
    field("name", "Name", value=getattr(l, "name", None), required=True),
    field("slug", "Slug (URL id)", value=getattr(l, "slug", None), help="Lowercase letters, digits, dashes. Auto-generated if blank."),
    field("address", "Street address", value=getattr(l, "address", None)),
    field("city", "City/Town", value=getattr(l, "city", "McAlester")),
    field("zip", "ZIP", value=getattr(l, "zip", None)),
    field("lat", "Latitude", "number", getattr(l, "lat", None), step="any"),
    field("lon", "Longitude", "number", getattr(l, "lon", None), step="any"),
    field("precinct", "Precinct", value=getattr(l, "precinct", None), help="Filled by Geocode when available."),
    field("status", "Status", "select", getattr(l, "status", "planned"), options=m.LOCATION_STATUSES),
    field("hours", "Hours", value=getattr(l, "hours", None), help='e.g. "Sat 9:00 a.m.–1:00 p.m."'),
    field("notes", "Notes", "textarea", getattr(l, "notes", None)),
    field("public", "Show on the public site", "checkbox", getattr(l, "public", True)),
]


def _slugify(v: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "-", (v or "").lower()).strip("-")[:60] or "location"


def _apply_loc(l: m.Location, form, db: Session):
    l.name = F.s(form, "name", l.name or "")
    slug = _slugify(F.s(form, "slug") or l.name)
    base, n = slug, 2
    while db.scalar(select(m.Location).where(m.Location.slug == slug, m.Location.id != (l.id or 0))):
        slug = f"{base}-{n}"; n += 1
    l.slug = slug
    l.address, l.city, l.zip = F.s(form, "address"), F.s(form, "city"), F.s(form, "zip")
    l.lat, l.lon, l.precinct = F.f(form, "lat"), F.f(form, "lon"), F.s(form, "precinct")
    l.status, l.hours, l.notes, l.public = F.s(form, "status", "planned"), F.s(form, "hours"), F.s(form, "notes"), F.b(form, "public")


@router.get("/locations", dependencies=AUTH)
def locations(request: Request, db: Session = Depends(get_db)):
    rows = db.scalars(select(m.Location).options(selectinload(m.Location.events)).order_by(m.Location.status, m.Location.name)).all()
    return render(request, "admin/locations.html", rows=rows)


@router.get("/locations/new", dependencies=AUTH)
def location_new(request: Request):
    return render(request, "admin/form.html", title="New signing location", fields=LOC_FIELDS(), action="/admin/locations/new", back="/admin/locations")


@router.post("/locations/new", dependencies=AUTH)
async def location_create(request: Request, db: Session = Depends(get_db)):
    form = await F.parse(request)
    if not F.s(form, "name"):
        return go("/admin/locations/new", err="Name is required.")
    l = m.Location(name=F.s(form, "name"), slug="tmp")
    db.add(l); db.flush()
    _apply_loc(l, form, db); db.commit()
    return go(f"/admin/locations/{l.id}", msg="Location added. Use Geocode to place it on the map.")


@router.get("/locations/{lid}", dependencies=AUTH)
def location_edit(request: Request, lid: int, db: Session = Depends(get_db)):
    l = db.get(m.Location, lid) or _404()
    evs = db.scalars(select(m.Event).where(m.Event.location_id == lid).order_by(m.Event.date)).all()
    extra = ('<div class="actions"><form method="post" action="/admin/locations/%d/geocode"><input type="hidden" name="csrf" value="%s">'
             '<button class="btn">Geocode &amp; find precinct</button></form>'
             '<form method="post" action="/admin/locations/%d/delete" onsubmit="return confirm(\'Delete this location and its events?\')">'
             '<input type="hidden" name="csrf" value="%s"><button class="btn danger">Delete</button></form></div>'
             % (lid, read_session(request)["csrf"], lid, read_session(request)["csrf"]))
    if evs:
        extra += "<h3>Events here</h3><ul>" + "".join(f'<li><a href="/admin/events/{e.id}">{e.date or "no date"} {e.start or ""}–{e.end or ""}</a>{" (hidden)" if not e.public else ""}</li>' for e in evs) + "</ul>"
    extra += f'<p><a class="btn" href="/admin/events/new?location={lid}">Add event here</a></p>'
    return render(request, "admin/form.html", title=f"Location: {l.name}", fields=LOC_FIELDS(l), action=f"/admin/locations/{lid}", back="/admin/locations", extra=extra)


@router.post("/locations/{lid}", dependencies=AUTH)
async def location_save(request: Request, lid: int, db: Session = Depends(get_db)):
    form = await F.parse(request)
    l = db.get(m.Location, lid) or _404()
    _apply_loc(l, form, db); db.commit()
    return go(f"/admin/locations/{lid}", msg="Location saved.")


@router.post("/locations/{lid}/delete", dependencies=AUTH)
async def location_delete(request: Request, lid: int, db: Session = Depends(get_db)):
    await F.parse(request)
    l = db.get(m.Location, lid) or _404()
    db.delete(l); db.commit()
    return go("/admin/locations", msg="Location deleted.")


@router.post("/locations/{lid}/geocode", dependencies=AUTH)
async def location_geocode(request: Request, lid: int, db: Session = Depends(get_db)):
    await F.parse(request)
    l = db.get(m.Location, lid) or _404()
    try:
        from toolkit.geo.lookup import PrecinctIndex
    except ImportError:
        return go(f"/admin/locations/{lid}", err="Geocoding is not available yet (toolkit.geo.lookup missing).")
    idx = getattr(request.app.state, "precinct_index", None) or PrecinctIndex()
    request.app.state.precinct_index = idx
    addr = ", ".join(x for x in [l.address, l.city, "OK", l.zip] if x)
    try:
        res = idx.lookup_address(addr)
    except Exception as e:
        return go(f"/admin/locations/{lid}", err=f"Geocode failed: {e}")
    lat = res.get("lat") or (res.get("point") or {}).get("lat")
    lon = res.get("lon") or (res.get("point") or {}).get("lon")
    pct = res.get("precinct") if not isinstance(res.get("precinct"), dict) else res["precinct"].get("precinct")
    if lat and lon:
        l.lat, l.lon = float(lat), float(lon)
    if pct:
        l.precinct = str(pct)
    db.commit()
    return go(f"/admin/locations/{lid}", msg=f"Geocoded: {l.lat}, {l.lon}; precinct {l.precinct or 'unknown'}." if lat else None,
              err=None if lat else f"No match for “{addr}”.")


def EVENT_FIELDS(db: Session, e=None, location_id=None):
    locs = [(str(l.id), l.name) for l in db.scalars(select(m.Location).order_by(m.Location.name)).all()]
    leads = [("", "—")] + [(str(c.id), c.name) for c in db.scalars(select(m.Circulator).where(m.Circulator.active.is_(True)).order_by(m.Circulator.name)).all()]
    return [
        field("location_id", "Location", "select", str(getattr(e, "location_id", location_id or "") or ""), options=locs, required=True),
        field("date", "Date", "date", getattr(e, "date", None)),
        field("start", "Start", "time", getattr(e, "start", None)),
        field("end", "End", "time", getattr(e, "end", None)),
        field("lead_id", "Event lead", "select", str(getattr(e, "lead_id", "") or ""), options=leads),
        field("volunteers_needed", "Volunteers needed", "number", getattr(e, "volunteers_needed", None)),
        field("pamphlets_issued", "Pamphlets issued", "number", getattr(e, "pamphlets_issued", None)),
        field("expected_signatures", "Expected signatures", "number", getattr(e, "expected_signatures", None)),
        field("notes", "Notes", "textarea", getattr(e, "notes", None)),
        field("public", "Show on the public site", "checkbox", getattr(e, "public", True)),
    ]


def _apply_event(e: m.Event, form):
    e.location_id = F.i(form, "location_id")
    e.date, e.start, e.end = F.d(form, "date"), F.t(form, "start"), F.t(form, "end")
    e.lead_id = F.i(form, "lead_id")
    e.volunteers_needed, e.pamphlets_issued, e.expected_signatures = F.i(form, "volunteers_needed"), F.i(form, "pamphlets_issued"), F.i(form, "expected_signatures")
    e.notes, e.public = F.s(form, "notes"), F.b(form, "public")


@router.get("/events", dependencies=AUTH)
def events(request: Request, when: str = "upcoming", db: Session = Depends(get_db)):
    stmt = select(m.Event).options(selectinload(m.Event.location), selectinload(m.Event.lead))
    if when == "upcoming":
        stmt = stmt.where((m.Event.date >= date.today()) | (m.Event.date.is_(None)))
    rows = db.scalars(stmt.order_by(m.Event.date, m.Event.start)).all()
    return render(request, "admin/events.html", rows=rows, when=when)


@router.get("/events/new", dependencies=AUTH)
def event_new(request: Request, location: int | None = None, db: Session = Depends(get_db)):
    if not db.scalar(select(func.count()).select_from(m.Location)):
        return go("/admin/locations/new", err="Add a location first.")
    return render(request, "admin/form.html", title="New event", fields=EVENT_FIELDS(db, location_id=location), action="/admin/events/new", back="/admin/events")


@router.post("/events/new", dependencies=AUTH)
async def event_create(request: Request, db: Session = Depends(get_db)):
    form = await F.parse(request)
    if not F.i(form, "location_id"):
        return go("/admin/events/new", err="Pick a location.")
    e = m.Event(location_id=F.i(form, "location_id"))
    _apply_event(e, form); db.add(e); db.commit()
    return go("/admin/events", msg="Event added.")


@router.get("/events/{eid}", dependencies=AUTH)
def event_edit(request: Request, eid: int, db: Session = Depends(get_db)):
    e = db.get(m.Event, eid) or _404()
    extra = ('<form method="post" action="/admin/events/%d/delete" onsubmit="return confirm(\'Delete this event?\')">'
             '<input type="hidden" name="csrf" value="%s"><button class="btn danger">Delete event</button></form>' % (eid, read_session(request)["csrf"]))
    return render(request, "admin/form.html", title="Event", fields=EVENT_FIELDS(db, e), action=f"/admin/events/{eid}", back="/admin/events", extra=extra)


@router.post("/events/{eid}", dependencies=AUTH)
async def event_save(request: Request, eid: int, db: Session = Depends(get_db)):
    form = await F.parse(request)
    e = db.get(m.Event, eid) or _404()
    _apply_event(e, form); db.commit()
    return go("/admin/events", msg="Event saved.")


@router.post("/events/{eid}/delete", dependencies=AUTH)
async def event_delete(request: Request, eid: int, db: Session = Depends(get_db)):
    await F.parse(request)
    e = db.get(m.Event, eid) or _404()
    db.delete(e); db.commit()
    return go("/admin/events", msg="Event deleted.")


# ---------- contacts ----------
CONTACT_FIELDS = lambda c=None: [
    field("role", "Role / what they help with", value=getattr(c, "role", None), required=True),
    field("name", "Name", value=getattr(c, "name", None)),
    field("phone", "Phone", value=getattr(c, "phone", None)),
    field("email", "Email", value=getattr(c, "email", None)),
    field("address", "Address", value=getattr(c, "address", None)),
    field("hours", "Hours", value=getattr(c, "hours", None)),
    field("sort_order", "Sort order", "number", getattr(c, "sort_order", 100)),
    field("public", "Show on the public site", "checkbox", getattr(c, "public", True)),
]


def _apply_contact(c: m.Contact, form):
    c.role, c.name, c.phone, c.email = F.s(form, "role", c.role or ""), F.s(form, "name"), F.s(form, "phone"), F.s(form, "email")
    c.address, c.hours, c.sort_order, c.public = F.s(form, "address"), F.s(form, "hours"), F.i(form, "sort_order", 100), F.b(form, "public")


@router.get("/contacts", dependencies=AUTH)
def contacts(request: Request, db: Session = Depends(get_db)):
    rows = db.scalars(select(m.Contact).order_by(m.Contact.sort_order, m.Contact.role)).all()
    return render(request, "admin/contacts.html", rows=rows)


@router.get("/contacts/new", dependencies=AUTH)
def contact_new(request: Request):
    return render(request, "admin/form.html", title="New contact", fields=CONTACT_FIELDS(), action="/admin/contacts/new", back="/admin/contacts")


@router.post("/contacts/new", dependencies=AUTH)
async def contact_create(request: Request, db: Session = Depends(get_db)):
    form = await F.parse(request)
    if not F.s(form, "role"):
        return go("/admin/contacts/new", err="Role is required.")
    c = m.Contact(role=F.s(form, "role")); _apply_contact(c, form); db.add(c); db.commit()
    return go("/admin/contacts", msg="Contact added.")


@router.get("/contacts/{cid}", dependencies=AUTH)
def contact_edit(request: Request, cid: int, db: Session = Depends(get_db)):
    c = db.get(m.Contact, cid) or _404()
    extra = ('<form method="post" action="/admin/contacts/%d/delete" onsubmit="return confirm(\'Delete this contact?\')">'
             '<input type="hidden" name="csrf" value="%s"><button class="btn danger">Delete</button></form>' % (cid, read_session(request)["csrf"]))
    return render(request, "admin/form.html", title=f"Contact: {c.role}", fields=CONTACT_FIELDS(c), action=f"/admin/contacts/{cid}", back="/admin/contacts", extra=extra)


@router.post("/contacts/{cid}", dependencies=AUTH)
async def contact_save(request: Request, cid: int, db: Session = Depends(get_db)):
    form = await F.parse(request)
    c = db.get(m.Contact, cid) or _404()
    _apply_contact(c, form); db.commit()
    return go("/admin/contacts", msg="Contact saved.")


@router.post("/contacts/{cid}/delete", dependencies=AUTH)
async def contact_delete(request: Request, cid: int, db: Session = Depends(get_db)):
    await F.parse(request)
    c = db.get(m.Contact, cid) or _404()
    db.delete(c); db.commit()
    return go("/admin/contacts", msg="Contact deleted.")


# ---------- QA tasks & records log ----------
@router.get("/qa", dependencies=AUTH)
def qa(request: Request, db: Session = Depends(get_db)):
    rows = db.scalars(select(m.QATask).order_by(m.QATask.sort_order, m.QATask.id)).all()
    return render(request, "admin/qa.html", rows=rows, statuses=m.QA_STATUSES)


@router.post("/qa/new", dependencies=AUTH)
async def qa_new(request: Request, db: Session = Depends(get_db)):
    form = await F.parse(request)
    if not F.s(form, "task"):
        return go("/admin/qa", err="Task text is required.")
    db.add(m.QATask(task=F.s(form, "task"), owner=F.s(form, "owner"), sort_order=F.i(form, "sort_order", 500))); db.commit()
    return go("/admin/qa", msg="Task added.")


@router.post("/qa/{tid}", dependencies=AUTH)
async def qa_update(request: Request, tid: int, db: Session = Depends(get_db)):
    form = await F.parse(request)
    t = db.get(m.QATask, tid) or _404()
    t.status, t.owner, t.notes = F.s(form, "status", t.status), F.s(form, "owner"), F.s(form, "notes")
    db.commit()
    return go("/admin/qa", msg="Updated.")


# ---------- documents (built PDFs) ----------
import json as _json
import re as _re
from pathlib import Path as _Path
from fastapi.responses import FileResponse
from toolkit import ROOT as _ROOT

_SAFE_NAME = _re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}\.pdf$")


def _docs_dirs() -> list[_Path]:
    """Where built PDFs live: dist/ (baked into the Docker image) or output/ (local `make docs`)."""
    import os
    env = os.environ.get("DOCS_DIRS")
    if env:
        return [_Path(p) for p in env.split(":") if p]
    cands = [_ROOT / "dist" / "docs", _ROOT / "dist" / "map", _ROOT / "output" / "docs", _ROOT / "output" / "map"]
    return [p for p in cands if p.is_dir()]


def _find_doc(name: str) -> _Path | None:
    if not _SAFE_NAME.match(name):
        return None
    for d in _docs_dirs():
        f = d / name
        if f.is_file() and f.resolve().parent == d.resolve():
            return f
    return None


@router.get("/documents", dependencies=AUTH)
def documents(request: Request):
    manifest, files, seen = None, [], set()
    for d in _docs_dirs():
        mp = d / "manifest.json"
        if manifest is None and mp.is_file():
            try:
                manifest = _json.loads(mp.read_text())
            except Exception:
                manifest = None
        for f in sorted(d.glob("*.pdf")):
            if f.name in seen:
                continue
            seen.add(f.name)
            meta = next((x for x in (manifest or {}).get("files", []) if x.get("name") == f.name), {})
            files.append({"name": f.name, "title": meta.get("title") or ("Precinct wall map (legal, landscape)" if "precincts" in f.name else f.stem),
                          "bytes": f.stat().st_size, "pages": meta.get("pages"), "sha256": (meta.get("sha256") or "")[:12]})
    return render(request, "admin/documents.html", files=files, manifest=manifest, dirs=[str(d) for d in _docs_dirs()])


@router.get("/documents/view/{name}", dependencies=AUTH)
def document_view(request: Request, name: str):
    f = _find_doc(name) or _404()
    return render(request, "admin/document_view.html", doc_name=name, size=f.stat().st_size)


@router.get("/documents/file/{name}", dependencies=AUTH)
def document_file(name: str, download: int = 0):
    f = _find_doc(name) or _404()
    return FileResponse(str(f), media_type="application/pdf", filename=name if download else None,
                        content_disposition_type="attachment" if download else "inline")


@router.get("/records", dependencies=AUTH)
def records(request: Request, db: Session = Depends(get_db)):
    rows = db.scalars(select(m.RecordsLog).order_by(desc(m.RecordsLog.occurred_at), desc(m.RecordsLog.id))).all()
    return render(request, "admin/records.html", rows=rows)


@router.post("/records/new", dependencies=AUTH)
async def records_new(request: Request, db: Session = Depends(get_db)):
    form = await F.parse(request)
    if not F.s(form, "item"):
        return go("/admin/records", err="Describe the item (e.g. 'True copy filed with Election Board').")
    when = F.s(form, "occurred_at")
    try:
        occurred = datetime.fromisoformat(when).replace(tzinfo=timezone.utc) if when else datetime.now(timezone.utc)
    except ValueError:
        occurred = datetime.now(timezone.utc)
    db.add(m.RecordsLog(item=F.s(form, "item"), office=F.s(form, "office"), person=F.s(form, "person"), documents=F.s(form, "documents"),
                        receipt_obtained=F.b(form, "receipt_obtained"), notes=F.s(form, "notes"), occurred_at=occurred))
    db.commit()
    return go("/admin/records", msg="Logged.")


# ---------- users (admin only) ----------
@router.get("/users", dependencies=[Depends(require_admin)])
def users(request: Request, db: Session = Depends(get_db)):
    rows = db.scalars(select(m.User).order_by(m.User.username)).all()
    return render(request, "admin/users.html", rows=rows)


@router.post("/users/new", dependencies=[Depends(require_admin)])
async def user_new(request: Request, db: Session = Depends(get_db)):
    form = await F.parse(request)
    u, pw, role = F.s(form, "username"), F.s(form, "password"), F.s(form, "role", "editor")
    if not u or not pw or len(pw) < 10:
        return go("/admin/users", err="Username and a password of at least 10 characters are required.")
    if db.scalar(select(m.User).where(m.User.username == u)):
        return go("/admin/users", err="That username exists.")
    db.add(m.User(username=u, password_hash=hash_password(pw), role=role if role in ("admin", "editor") else "editor")); db.commit()
    return go("/admin/users", msg=f"Added {u}.")


@router.post("/users/{uid}/toggle", dependencies=[Depends(require_admin)])
async def user_toggle(request: Request, uid: int, db: Session = Depends(get_db), me: m.User = Depends(require_admin)):
    await F.parse(request)
    u = db.get(m.User, uid) or _404()
    if u.id == me.id:
        return go("/admin/users", err="You cannot deactivate yourself.")
    u.active = not u.active; db.commit()
    return go("/admin/users", msg=f"{u.username} {'activated' if u.active else 'deactivated'}.")


@router.post("/users/{uid}/reset", dependencies=[Depends(require_admin)])
async def user_reset(request: Request, uid: int, db: Session = Depends(get_db)):
    form = await F.parse(request)
    u = db.get(m.User, uid) or _404()
    pw = F.s(form, "password")
    if not pw or len(pw) < 10:
        return go("/admin/users", err="New password must be at least 10 characters.")
    u.password_hash = hash_password(pw); db.commit()
    return go("/admin/users", msg=f"Password reset for {u.username}.")


# ---------- export / import ----------
@router.get("/export.xlsx", dependencies=AUTH)
def export_xlsx(request: Request, db: Session = Depends(get_db)):
    try:
        from toolkit.xlsx.export import build_workbook
    except ImportError:
        raise HTTPException(503, "Workbook export is not available yet.")
    wb = build_workbook(db, settings=Settings(db))
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    name = f"petition-master-{date.today().isoformat()}.xlsx"
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/import", dependencies=AUTH)
def import_form(request: Request):
    return render(request, "admin/import.html")


@router.post("/import", dependencies=AUTH)
async def import_tracker(request: Request, db: Session = Depends(get_db)):
    form = await F.parse(request)
    up = form.get("file")
    if not isinstance(up, UploadFile) or not up.filename:
        return go("/admin/import", err="Choose the tracker .xlsx file.")
    try:
        from toolkit.xlsx.import_tracker import import_tracker as do_import
    except ImportError:
        raise HTTPException(503, "Tracker import is not available yet.")
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        tmp.write(await up.read()); path = tmp.name
    try:
        summary = do_import(path, db)
        db.commit()
    except Exception as e:
        db.rollback()
        return go("/admin/import", err=f"Import failed: {e}")
    finally:
        os.unlink(path)
    return render(request, "admin/import.html", summary=summary, msg="Import finished.")
