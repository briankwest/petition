"""Download precinct/county/district layers from the OU Center for Spatial Analysis ArcGIS
service (the State Election Board's mapping contractor) and build the simplified web file.

    python -m toolkit.geo.fetch          # precincts + web file
    python -m toolkit.geo.fetch --all    # + county, commissioner districts, municipalities, lakes, roads
"""
from __future__ import annotations
import argparse, csv, json, re, sys, datetime as dt
import requests
from shapely.geometry import shape, mapping, MultiPolygon
from shapely.ops import unary_union, polygonize, linemerge
from shapely import set_precision
from shapely.validation import make_valid
from . import PRECINCT_DIR, RAW_PRECINCTS, WEB_PRECINCTS, POLLING_PLACES

SERVICE = "https://services7.arcgis.com/cpyRdAfuizCFzBhp/arcgis/rest/services/Pittsburg_County_Data/FeatureServer"
LAYERS = {  # name -> (layer id, output file)
    "precincts": (10, "pittsburg_pct2020.geojson"),
    "county": (0, "county.geojson"),
    "commissioner_districts": (2, "commissioner_districts.geojson"),
    "municipalities": (8, "municipalities.geojson"),
    "lakes": (7, "lakes.geojson"),
    "roads": (15, "roads.geojson"),
}
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
KEEP_PRECINCT_PROPS = ["Precinct", "PCT_CEB", "P0010001", "P0030001", "St_house", "St_senate", "Comm", "Uscong", "COUNTY_NAM", "CO_FIPS", "GeoID"]


def query_layer(layer_id: int, page: int = 2000, timeout: int = 60) -> dict:
    """Fetch every feature from a layer as GeoJSON (EPSG:4326), paging past maxRecordCount."""
    features, offset = [], 0
    while True:
        url = f"{SERVICE}/{layer_id}/query"
        params = {"where": "1=1", "outFields": "*", "outSR": 4326, "f": "geojson",
                  "resultOffset": offset, "resultRecordCount": page}
        r = requests.get(url, params=params, headers=UA, timeout=timeout)
        r.raise_for_status()
        g = r.json()
        if "error" in g:
            raise RuntimeError(g["error"])
        feats = g.get("features", [])
        features.extend(feats)
        if not g.get("properties", {}).get("exceededTransferLimit") and len(feats) < page:
            break
        if not feats:
            break
        offset += len(feats)
    return {"type": "FeatureCollection", "features": features}


def load_polling_places() -> dict[int, dict]:
    with open(POLLING_PLACES, newline="", encoding="utf-8") as f:
        return {int(r["precinct"]): r for r in csv.DictReader(f)}


def source_block(layer_id: int, note: str = "") -> dict:
    return {"service": f"{SERVICE}/{layer_id}", "publisher": "OU Center for Spatial Analysis (contracted by the Oklahoma State Election Board)",
            "retrieved": dt.date.today().isoformat(), "crs": "EPSG:4326", "note": note}


def clean_precincts(raw: dict) -> dict:
    feats = []
    for f in raw["features"]:
        p = f["properties"]
        props = {k: p.get(k) for k in KEEP_PRECINCT_PROPS}
        props["precinct_num"] = int(props["Precinct"])
        feats.append({"type": "Feature", "properties": props, "geometry": f["geometry"]})
    feats.sort(key=lambda f: f["properties"]["precinct_num"])
    return {"type": "FeatureCollection", "features": feats,
            "source": source_block(10, "P0010001 = 2020 Census total population; P0030001 = 2020 Census voting-age population (18+). Not registered-voter counts.")}


def simplify_shared(geoms: list, tolerance: float, grid: float = 1e-5) -> list:
    """Topology-aware simplification: snap vertices to a ~1 m grid so neighbouring boundaries
    coincide, node every boundary into shared linework, merge segments between junctions,
    simplify the shared lines (junction nodes are kept, so neighbours stay glued), re-polygonize,
    and hand each piece back to the precinct that contains its representative point.
    No slivers, no overlaps: with the 2020 data this yields exactly 38 pieces."""
    snapped = [set_precision(g, grid) for g in geoms]
    lines = unary_union([g.boundary for g in snapped])
    merged = linemerge(lines) if lines.geom_type == "MultiLineString" else lines
    simp = merged.simplify(tolerance, preserve_topology=True)
    pieces = list(polygonize(unary_union(simp)))
    out = [[] for _ in geoms]
    for piece in pieces:
        rp = piece.representative_point()
        best, best_d = None, None
        for i, g in enumerate(geoms):
            if g.contains(rp):
                best = i; break
            d = g.distance(rp)
            if best_d is None or d < best_d:
                best, best_d = i, d
        out[best].append(piece)
    result = []
    for i, parts in enumerate(out):
        if not parts:
            result.append(geoms[i].simplify(tolerance, preserve_topology=True)); continue
        u = unary_union(parts)
        result.append(u if not u.is_empty else geoms[i])
    return result


def build_web(raw: dict, tolerance: float = 0.0005) -> dict:
    """Simplified precincts (shared edges) with clean properties for the browser."""
    pp = load_polling_places()
    feats_raw = sorted(raw["features"], key=lambda f: int(f["properties"].get("precinct_num") or f["properties"]["Precinct"]))
    geoms = [make_valid(shape(f["geometry"])) for f in feats_raw]
    simplified = simplify_shared(geoms, tolerance)
    feats = []
    for f, geom, simp in zip(feats_raw, geoms, simplified):
        p = f["properties"]
        num = int(p.get("precinct_num") or p["Precinct"])
        rp = geom.representative_point()
        place = pp.get(num, {})
        props = {
            "precinct": num,
            "pct_ceb": p.get("PCT_CEB"),
            "polling_place": place.get("polling_place"),
            "address": place.get("address"),
            "city": place.get("city"),
            "pop2020": int(p.get("P0010001") or 0),
            "vap2020": int(p.get("P0030001") or 0),
            "comm": int(p.get("Comm") or 0),
            "label_lat": round(rp.y, 5),
            "label_lon": round(rp.x, 5),
        }
        g = json.loads(json.dumps(mapping(simp)), parse_float=lambda x: round(float(x), 5))
        feats.append({"type": "Feature", "id": num, "properties": props, "geometry": g})
    return {"type": "FeatureCollection", "features": feats,
            "source": source_block(10, f"Simplified with shared-edge topology (tolerance {tolerance} deg) from pittsburg_pct2020.geojson; polling places joined from polling_places.csv.")}


MAJOR_ROAD_TYPES = {"TURNPIKE", "EXPRESSWAY", "HIGHWAY", "TPKE", "EXPY", "HWY"}
_MAJOR_NAME = re.compile(r"\b(HIGHWAY|HWY|TURNPIKE|EXPRESSWAY|INDIAN NATION|US[- ]?\d+|SH[- ]?\d+|STATE HWY)\b", re.I)


def major_roads(fc: dict) -> dict:
    """Keep highway-class roads only (the full centerline file is ~17 MB)."""
    keep = []
    for f in fc["features"]:
        p = f["properties"]
        name = " ".join(str(p.get(k) or "") for k in ("pretype", "fullname", "altstname1"))
        if (str(p.get("streettype") or "").upper() in MAJOR_ROAD_TYPES or str(p.get("pretype") or "").upper() == "HIGHWAY"
                or _MAJOR_NAME.search(name)):
            keep.append({"type": "Feature", "properties": {"name": p.get("fullname"), "type": p.get("streettype"), "alt": p.get("altstname1")},
                         "geometry": f["geometry"]})
    return {"type": "FeatureCollection", "features": keep, "source": dict(fc.get("source", {}), note="Highway-class centerlines only (filtered from the full PSAP road centerline layer).")}


def write(path, obj) -> int:
    path.write_text(json.dumps(obj, separators=(",", ":")), encoding="utf-8")
    return path.stat().st_size


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true", help="also fetch county, commissioner districts, municipalities, lakes, roads")
    ap.add_argument("--offline", action="store_true", help="skip downloads; rebuild the web file from the raw precinct file")
    ap.add_argument("--tolerance", type=float, default=0.0005)
    ap.add_argument("--full-roads", action="store_true", help="keep every road centerline (~17 MB) instead of highways only")
    a = ap.parse_args(argv)
    PRECINCT_DIR.mkdir(parents=True, exist_ok=True)

    if a.offline:
        raw = json.loads(RAW_PRECINCTS.read_text(encoding="utf-8"))
    else:
        raw = clean_precincts(query_layer(10))
        n = write(RAW_PRECINCTS, raw)
        print(f"precincts: {len(raw['features'])} features -> {RAW_PRECINCTS.name} ({n:,} bytes)")
        if a.all:
            for name, (lid, fname) in LAYERS.items():
                if name == "precincts":
                    continue
                g = query_layer(lid)
                g["source"] = source_block(lid)
                if name == "roads" and not a.full_roads:
                    g = major_roads(g)
                n = write(PRECINCT_DIR / fname, g)
                print(f"{name}: {len(g['features'])} features -> {fname} ({n:,} bytes)")

    web = build_web(raw, a.tolerance)
    n = write(WEB_PRECINCTS, web)
    print(f"web precincts: {len(web['features'])} features -> {WEB_PRECINCTS.name} ({n:,} bytes)")
    if n > 250_000:
        print("WARNING: web file exceeds 250 KB; raise --tolerance", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
