"""Address → precinct lookup. Pure functions; no web-framework imports.

    idx = PrecinctIndex()
    idx.find(35.93, -95.77)              -> precinct properties dict or None
    idx.geocode("801 N 9th St, McAlester")  -> {"lat","lon","matched_address"} or None
    idx.lookup_address("801 N 9th St, McAlester", points=[...]) -> combined result
"""
from __future__ import annotations
import json, math, re
from functools import lru_cache
import requests
from shapely.geometry import shape, Point
from shapely.strtree import STRtree
from shapely.prepared import prep
from . import WEB_PRECINCTS, RAW_PRECINCTS

CENSUS_URL = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
UA = {"User-Agent": "petition.mcalester.net precinct finder (Pittsburg County, OK)"}
_STATE_RE = re.compile(r"\b(OK|Oklahoma)\b", re.I)
_DIR_RE = re.compile(r"^\s*\d+[A-Za-z]?\s+(N|S|E|W|NE|NW|SE|SW|NORTH|SOUTH|EAST|WEST)\b\.?", re.I)
_DIR_NORM = {"NORTH": "N", "SOUTH": "S", "EAST": "E", "WEST": "W"}


def _directional(addr: str) -> str | None:
    m = _DIR_RE.match(addr or "")
    if not m:
        return None
    d = m.group(1).upper()
    return _DIR_NORM.get(d, d)


def _census(q: str, timeout: float) -> dict | None:
    try:
        r = requests.get(CENSUS_URL, params={"address": q, "benchmark": "Public_AR_Current", "format": "json"},
                         headers=UA, timeout=timeout)
        r.raise_for_status()
        matches = r.json().get("result", {}).get("addressMatches", [])
    except (requests.RequestException, ValueError):
        return None
    if not matches:
        return None
    m = matches[0]
    return {"lat": float(m["coordinates"]["y"]), "lon": float(m["coordinates"]["x"]),
            "matched_address": m.get("matchedAddress"), "source": "census"}


def _nominatim(q: str, timeout: float) -> dict | None:
    """OpenStreetMap Nominatim — fallback only (usage policy: ≤1 req/s, identify the app)."""
    try:
        r = requests.get(NOMINATIM_URL, params={"q": q, "format": "jsonv2", "limit": 3, "countrycodes": "us"},
                         headers=UA, timeout=timeout)
        r.raise_for_status()
        rows = r.json()
    except (requests.RequestException, ValueError):
        return None
    # only accept address-level hits; a city/county/boundary centroid is not a geocode of the address
    rows = [m for m in rows if m.get("class") not in ("place", "boundary") or m.get("type") in ("house", "postcode")]
    if not rows:
        return None
    m = rows[0]
    return {"lat": float(m["lat"]), "lon": float(m["lon"]), "matched_address": m.get("display_name"), "source": "nominatim"}


def haversine_mi(lat1, lon1, lat2, lon2) -> float:
    r = 3958.7613
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def geocode(address: str, timeout: float = 8.0) -> dict | None:
    """Census Bureau public geocoder (no key), with OpenStreetMap Nominatim as a fallback when
    Census has no match or matches the wrong street directional. Returns
    {lat, lon, matched_address, source[, confidence, note]} or None."""
    # normalise: drop periods ("N." "St."), collapse whitespace/commas, add the state if missing
    q = re.sub(r"\s*,\s*", ", ", re.sub(r"\s+", " ", (address or "").replace(".", " "))).strip(" ,")
    if not q:
        return None
    if not _STATE_RE.search(q):
        q = f"{q}, OK"
    g = _census(q, timeout)
    want = _directional(q)
    if g and want and (_directional(g["matched_address"] or "") not in (None, want)):
        # Census snapped to the wrong side of town (e.g. "801 N 9th" -> "801 S 9TH ST"); try OSM.
        alt = _nominatim(q, timeout)
        if alt:
            alt["note"] = f"Census matched {g['matched_address']!r}; used OpenStreetMap instead"
            return alt
        g["confidence"] = "low"
        g["note"] = "Matched street direction differs from the address you entered"
        return g
    if g:
        return g
    return _nominatim(q, timeout)


def nearest(lat: float, lon: float, points: list[dict], limit: int | None = None) -> list[dict]:
    """Sort dicts with lat/lon by distance from (lat, lon); adds distance_mi. Skips points without coords."""
    out = []
    for p in points or []:
        plat, plon = p.get("lat"), p.get("lon")
        if plat is None or plon is None:
            continue
        d = dict(p)
        d["distance_mi"] = round(haversine_mi(lat, lon, float(plat), float(plon)), 2)
        out.append(d)
    out.sort(key=lambda d: d["distance_mi"])
    return out[:limit] if limit else out


class PrecinctIndex:
    def __init__(self, path=None):
        self.path = path or (WEB_PRECINCTS if WEB_PRECINCTS.exists() else RAW_PRECINCTS)
        fc = json.loads(self.path.read_text(encoding="utf-8"))
        self.props = [f["properties"] for f in fc["features"]]
        self.geoms = [shape(f["geometry"]) for f in fc["features"]]
        self._prepared = [prep(g) for g in self.geoms]
        self.tree = STRtree(self.geoms)
        self.bounds = self._bounds()

    def _bounds(self):
        xs = [g.bounds for g in self.geoms]
        return (min(b[0] for b in xs), min(b[1] for b in xs), max(b[2] for b in xs), max(b[3] for b in xs))

    def __len__(self):
        return len(self.geoms)

    def find(self, lat: float, lon: float) -> dict | None:
        pt = Point(float(lon), float(lat))
        for i in self.tree.query(pt):
            if self._prepared[int(i)].intersects(pt):
                return dict(self.props[int(i)])
        return None

    geocode = staticmethod(geocode)
    nearest = staticmethod(nearest)

    def lookup_address(self, address: str, points: list[dict] | None = None, limit: int = 5) -> dict:
        g = geocode(address)
        res = {"query": address, "matched_address": None, "lat": None, "lon": None, "precinct": None, "nearest": []}
        if not g:
            res["error"] = "Address not found. Try adding the city and ZIP code."
            return res
        res.update(g)
        res["precinct"] = self.find(g["lat"], g["lon"])
        if res["precinct"] is None:
            res["error"] = "That address is outside Pittsburg County."
        res["nearest"] = nearest(g["lat"], g["lon"], points or [], limit=limit)
        return res


@lru_cache(maxsize=1)
def default_index() -> PrecinctIndex:
    return PrecinctIndex()
