"""Public pages: neutral, plain language, no voter data collected."""
from __future__ import annotations
import os
import time
from collections import defaultdict, deque
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import Location, Event, Contact, VolunteerSignup, SIGNUP_ROLES
from ..settings import Settings
from ..stats import signature_stats
from ..auth import current_user, secret_key
from .. import market
from .. import forms as F
from . import render
from toolkit import statutes
from toolkit.letters import tokens as portal_tokens
from toolkit.letters import data as letter_data

router = APIRouter(dependencies=[Depends(current_user)])


def _upcoming(db: Session, limit: int = 10):
    return db.scalars(
        select(Event).join(Location).where(Event.public.is_(True), Location.public.is_(True),
                                           Event.date.is_not(None), Event.date >= date.today())
        .order_by(Event.date, Event.start).limit(limit)).all()


def _public_stats(db: Session, s: Settings):
    if not s.bool("public_show_counts"):
        return None
    return signature_stats(db, s)


def _targets(db: Session, s: Settings) -> dict:
    """The threshold numbers the campaign plans against, from the same settings the admin dashboard and
    the XLSX export read — shown on the home page whether or not the collected counts are public."""
    st = signature_stats(db, s)
    oc = s.raw("overcollect_fraction")
    return {"registered_voters": st["registered_voters"], "legal_minimum": st["legal_minimum"], "target": st["target"],
            "est_valid_rate": st["est_valid_rate"], "days_remaining": st["days_remaining"], "filing_deadline": st["filing_deadline"],
            # the source string carries an internal to-do after ';' (config/petition.yaml); only the citation is public
            "registered_voters_date": s.raw("registered_voters_date"),
            "registered_voters_source": (s.raw("registered_voters_source") or "").split(";")[0].strip() or None,
            "overcollect_pct": round(float(oc) * 100) if oc else None}


@router.get("/")
def home(request: Request, db: Session = Depends(get_db)):
    s = Settings(db)
    return render(request, "public/home.html", s=s, stats=_public_stats(db, s), targets=_targets(db, s), events=_upcoming(db, 5),
                  show_progress=s.bool("public_show_progress"))


@router.get("/sign")
def sign(request: Request, db: Session = Depends(get_db)):
    s = Settings(db)
    locations = db.scalars(select(Location).where(Location.public.is_(True), Location.status != "closed")
                           .order_by(Location.status.desc(), Location.name)).all()
    return render(request, "public/sign.html", s=s, locations=locations, events=_upcoming(db, 30))


@router.get("/registered")
def registered(request: Request, db: Session = Depends(get_db)):
    return render(request, "public/registered.html", s=Settings(db))


@router.get("/contact")
def contact(request: Request, db: Session = Depends(get_db)):
    contacts = db.scalars(select(Contact).where(Contact.public.is_(True)).order_by(Contact.sort_order, Contact.role)).all()
    return render(request, "public/contact.html", s=Settings(db), contacts=contacts)


@router.get("/faq")
def faq(request: Request, db: Session = Depends(get_db)):
    return render(request, "public/faq.html", s=Settings(db), exclusions=statutes.exclusions(),
                  five=statutes.FIVE_DATA_POINTS, cites={k: (statutes.html_url(k) or statutes.cite_url(k)) for k in ["62-868", "34-1", "34-3", "34-6", "34-6.1", "34-23"]})


@router.get("/childress-kiowa")
def childress_kiowa(request: Request, db: Session = Depends(get_db)):
    """Childress vs. Kiowa — the two IREN deals side by side; second item in the site nav."""
    return render(request, "public/sites.html", s=Settings(db))


@router.get("/tldr")
def tldr(request: Request, db: Session = Depends(get_db)):
    """The one-page version — the whole case on one Letter sheet with a QR code to the site; prints as a flyer."""
    s = Settings(db)
    if request.query_params.get("embed"):
        return render(request, "public/_tldr_sheet.html", s=s, targets=_targets(db, s))   # bare sheet for the modal
    return render(request, "public/tldr.html", s=s, targets=_targets(db, s))


@router.get("/questions")
def questions(request: Request, db: Session = Depends(get_db)):
    """Questions for the Board — the two dossiers' findings put to the commissioners; prints as a letter."""
    return render(request, "public/questions.html", s=Settings(db))


@router.get("/timeline")
def timeline(request: Request, db: Session = Depends(get_db)):
    # The dated record from IREN's June 2025 deposits to the tabled vote. Static: every line is a filed document.
    return render(request, "public/timeline.html", s=Settings(db))


@router.get("/r/{token}")
def portal(token: str, request: Request, db: Session = Depends(get_db)):
    """The page a records custodian reaches from the QR code or URL printed in a request letter. Until the response
    portal ships this is a holding page that names the request and says how to reply meanwhile; the token is matched
    against the committed hashes only, so an unknown or retired token is an ordinary 404 and nothing is recorded."""
    e = portal_tokens.lookup(token)
    if not e:
        raise HTTPException(status_code=404)
    letter = next((x for x in letter_data.letters() if x["n"] == e["n"]), None)
    # path drives the canonical and og:url tags; the token must never be echoed into the page
    return render(request, "public/portal_holding.html", s=Settings(db), entry=e, letter=letter, path="/r")


@router.get("/iren")
def iren(request: Request, db: Session = Depends(get_db)):
    """The IREN File — company dossier; first item in the site nav."""
    s = Settings(db)
    show = s.bool("public_show_market")
    q = market.get_quote(db) if show else None    # cache only: the page never waits on the feed
    return render(request, "public/iren.html", s=s, show_market=show, quote=q, q=market.display(q))


# ---- volunteer sign-up: no CAPTCHA; honeypot + signed timestamp + per-IP limit ----
def _signup_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(secret_key(), salt="volunteer-signup")


_signup_hits: dict[str, deque] = defaultdict(deque)


def _signup_allowed(request: Request, limit: int = 5, window: int = 3600) -> bool:
    ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "?")).split(",")[0].strip()
    q, now = _signup_hits[ip], time.time()
    while q and now - q[0] > window:
        q.popleft()
    if len(q) >= limit:
        return False
    q.append(now)
    return True


def _volunteer_ctx(db: Session):
    s = Settings(db)
    contacts = db.scalars(select(Contact).where(Contact.public.is_(True)).order_by(Contact.sort_order)).all()
    return s, contacts


@router.get("/volunteer")
def volunteer(request: Request, db: Session = Depends(get_db)):
    s, contacts = _volunteer_ctx(db)
    return render(request, "public/volunteer.html", s=s, contacts=contacts, form_url=s.raw("volunteer_form_url"),
                  roles=SIGNUP_ROLES, token=_signup_serializer().dumps(int(time.time())), values={}, errors=[])


@router.post("/volunteer")
async def volunteer_submit(request: Request, db: Session = Depends(get_db)):
    form = await F.parse(request, csrf=False)          # anonymous visitors have no session; see checks below
    s, contacts = _volunteer_ctx(db)
    if s.raw("volunteer_form_url"):
        return RedirectResponse("/volunteer", status_code=303)
    # bot checks: honeypot filled, or the form came back faster than a person can type
    min_seconds = int(os.environ.get("SIGNUP_MIN_SECONDS", "3"))
    try:
        issued = _signup_serializer().loads(F.s(form, "t") or "", max_age=86400)
        human = not F.s(form, "website") and (time.time() - int(issued)) >= min_seconds
    except (BadSignature, SignatureExpired, ValueError):
        human = False
    values = {k: F.s(form, k) or "" for k in ("name", "phone", "email", "city", "zip", "availability", "notes")}
    values["roles"] = F.lst(form, "roles")
    values["says_registered_voter"] = F.b(form, "says_registered_voter")
    values["says_18"] = F.b(form, "says_18")
    errors = []
    if not values["name"]:
        errors.append("Please enter your name.")
    if not values["phone"] and not values["email"]:
        errors.append("Please give a phone number or an email address so the Petition Captain can reach you.")
    bad_roles = [r for r in values["roles"] if r not in SIGNUP_ROLES]
    if bad_roles:
        errors.append("Please choose from the listed roles.")
    if errors:
        return render(request, "public/volunteer.html", status_code=400, s=s, contacts=contacts, form_url=None,
                      roles=SIGNUP_ROLES, token=_signup_serializer().dumps(int(time.time())), values=values, errors=errors)
    if human and _signup_allowed(request):
        db.add(VolunteerSignup(
            name=values["name"][:120], phone=values["phone"][:32] or None, email=values["email"][:120] or None,
            city=values["city"][:80] or None, zip=values["zip"][:10] or None,
            roles=",".join(values["roles"]) or "Circulator", says_registered_voter=values["says_registered_voter"],
            says_18=values["says_18"], availability=values["availability"][:2000] or None, notes=values["notes"][:2000] or None,
            ip=(request.headers.get("x-forwarded-for") or (request.client.host if request.client else None) or "")[:64] or None,
        ))
        db.commit()
    # bots and over-limit clients get the same thank-you page; nothing is stored for them
    return RedirectResponse("/volunteer/thanks", status_code=303)


@router.get("/volunteer/thanks")
def volunteer_thanks(request: Request, db: Session = Depends(get_db)):
    s, contacts = _volunteer_ctx(db)
    return render(request, "public/volunteer_thanks.html", s=s, contacts=contacts)
