"""JSON/GeoJSON endpoints used by the map and the public counts block."""
from __future__ import annotations
import time
from collections import defaultdict, deque
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import Location, Event
from ..settings import Settings
from ..stats import signature_stats
from .. import market

router = APIRouter(prefix="/api")
_hits: dict[str, deque] = defaultdict(deque)
RATE = (20, 60)  # 20 requests / 60 s per IP


def _rate_limit(request: Request) -> None:
    ip = (request.headers.get("x-forwarded-for") or request.client.host or "?").split(",")[0].strip()
    q, now = _hits[ip], time.time()
    while q and now - q[0] > RATE[1]:
        q.popleft()
    if len(q) >= RATE[0]:
        raise HTTPException(status_code=429, detail="Too many lookups — try again in a minute.")
    q.append(now)


def _next_event_for(db: Session, loc: Location):
    ev = db.scalars(select(Event).where(Event.location_id == loc.id, Event.public.is_(True), Event.date.is_not(None),
                                        Event.date >= date.today()).order_by(Event.date, Event.start).limit(1)).first()
    return {"date": ev.date.isoformat(), "start": ev.start.isoformat() if ev.start else None,
            "end": ev.end.isoformat() if ev.end else None} if ev else None


def public_points(db: Session) -> list[dict]:
    locs = db.scalars(select(Location).where(Location.public.is_(True), Location.status != "closed")).all()
    return [{"slug": l.slug, "name": l.name, "address": l.address, "city": l.city, "zip": l.zip, "lat": l.lat,
             "lon": l.lon, "hours": l.hours, "status": l.status, "precinct": l.precinct, "next_event": _next_event_for(db, l)}
            for l in locs]


@router.get("/stats.json")
def stats(db: Session = Depends(get_db)):
    s = Settings(db)
    base = {"site_status": s.raw("site_status"), "banner": s.raw("banner"), "public": s.bool("public_show_counts"),
            "adoption_date": s.adoption_date.isoformat() if s.adoption_date else None,
            "filing_deadline": s.filing_deadline.isoformat() if s.filing_deadline else None}
    if not s.bool("public_show_counts"):
        return base
    st = signature_stats(db, s)
    keys = ["as_of", "collected", "valid_estimate", "est_valid", "legal_minimum", "target", "remaining_to_target",
            "days_remaining", "registered_voters"]
    base.update({k: st[k] for k in keys})
    if s.bool("public_show_progress"):
        base.update({k: st[k] for k in ["progress_to_legal", "progress_to_target"]})
    return base


@router.get("/locations.geojson")
def locations_geojson(db: Session = Depends(get_db)):
    pts = public_points(db)
    feats = [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [p["lon"], p["lat"]]},
              "properties": {k: v for k, v in p.items() if k not in ("lat", "lon")}} for p in pts if p["lat"] and p["lon"]]
    unmapped = [{k: v for k, v in p.items() if k not in ("lat", "lon")} for p in pts if not (p["lat"] and p["lon"])]
    return JSONResponse({"type": "FeatureCollection", "features": feats, "unmapped": unmapped})


@router.get("/events.json")
def events_json(db: Session = Depends(get_db)):
    evs = db.scalars(select(Event).join(Location).where(Event.public.is_(True), Location.public.is_(True), Event.date.is_not(None),
                                                       Event.date >= date.today()).order_by(Event.date, Event.start)).all()
    return [{"id": e.id, "date": e.date.isoformat(), "start": e.start.isoformat() if e.start else None,
             "end": e.end.isoformat() if e.end else None, "location": e.location.name, "address": e.location.address,
             "city": e.location.city, "slug": e.location.slug, "notes": e.notes} for e in evs]


@router.get("/precinct")
def precinct(request: Request, address: str = "", db: Session = Depends(get_db)):
    address = (address or "").strip()
    if not address:
        raise HTTPException(status_code=400, detail="Enter a street address in Pittsburg County.")
    _rate_limit(request)
    try:
        from toolkit.geo.lookup import PrecinctIndex
    except ImportError:
        raise HTTPException(status_code=503, detail="Precinct lookup is not available yet.")
    idx = getattr(request.app.state, "precinct_index", None)
    if idx is None:
        idx = PrecinctIndex()
        request.app.state.precinct_index = idx
    points = [p for p in public_points(db) if p["lat"] and p["lon"]]
    try:
        result = idx.lookup_address(address, points=points)
    except Exception as e:  # upstream geocoder problems should not 500
        raise HTTPException(status_code=502, detail=f"Lookup failed: {e}")
    return JSONResponse(result)


@router.get("/quote.json")
def quote(request: Request, db: Session = Depends(get_db)):
    """Live IREN quote for the ticker on /iren. Public feed, cached server-side; the page
    renders from the cache and calls this to refresh, so this one may wait on the network."""
    _rate_limit(request)
    q = market.get_quote(db, block=True) if Settings(db).bool("public_show_market") else None
    if q is None:
        return JSONResponse({"ok": False, "symbol": market.SYMBOL}, status_code=503,
                            headers={"Cache-Control": "no-store"})
    return JSONResponse({"ok": True, "display": market.display(q), "spark": q.spark},
                        headers={"Cache-Control": "public, max-age=60"})
