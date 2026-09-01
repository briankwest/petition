"""Build the standalone interactive map and the legal-size wall map.

    python -m toolkit.geo.build_map --out output/map

Outputs:
  output/map/index.html                 standalone Leaflet map (Leaflet from cdnjs; everything else local)
  output/map/map.js, map.css            copied from app/static/
  output/map/data/*.geojson             precincts (web), county, districts, municipalities, locations
  output/map/pittsburg-precincts-legal.pdf   8.5 x 14 in (portrait) wall map: large map on top, polling places below
"""
from __future__ import annotations
import argparse, csv, json, shutil, sys, datetime as dt
from pathlib import Path
import yaml
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import PathPatch
from matplotlib.path import Path as MPath
from shapely.geometry import shape
from . import PRECINCT_DIR, WEB_PRECINCTS, POLLING_PLACES, SIGNING_LOCATIONS, STATIC_DIR
from .. import ROOT

CDN_CSS = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css"
CDN_JS = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"
LAYER_FILES = {"county": "county.geojson", "districts": "commissioner_districts.geojson",
               "municipalities": "municipalities.geojson", "lakes": "lakes.geojson", "roads": "roads.geojson"}


def locations_geojson(path=SIGNING_LOCATIONS) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    feats = []
    for loc in data.get("locations") or []:
        if loc.get("lat") is None or loc.get("lon") is None:
            continue
        props = {k: loc.get(k) for k in ("id", "name", "address", "city", "zip", "hours", "status", "notes", "precinct")}
        feats.append({"type": "Feature", "properties": props,
                      "geometry": {"type": "Point", "coordinates": [float(loc["lon"]), float(loc["lat"])]}})
    return {"type": "FeatureCollection", "features": feats}


HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pittsburg County Precincts — Petition Map</title>
<link rel="stylesheet" href="{css}">
<link rel="stylesheet" href="map.css">
<style>
  html,body{{margin:0;height:100%;font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}}
  header{{padding:10px 16px;border-bottom:1px solid #ddd7d3;background:#f8f7f5;display:flex;gap:16px;align-items:baseline;flex-wrap:wrap}}
  header h1{{font-size:17px;margin:0}} header p{{margin:0;font-size:13px;color:#6b625f}}
  #map{{height:calc(100% - 52px)}}
</style>
</head>
<body>
<header><h1>Pittsburg County, Oklahoma — voting precincts &amp; petition signing locations</h1>
<p>Precinct boundaries: OU Center for Spatial Analysis / Oklahoma State Election Board (2020). Built {date}.</p></header>
<div id="map"></div>
<script src="{js}"></script>
<script src="map.js"></script>
<script>
  initPetitionMap(document.getElementById('map'), {{
    precinctsUrl: 'data/pittsburg_web.geojson',
    locationsUrl: 'data/locations.geojson',
    pollingPlaces: true,
    countyUrl: 'data/county.geojson',
    districtsUrl: 'data/commissioner_districts.geojson',
    municipalitiesUrl: 'data/municipalities.geojson'
  }});
</script>
</body>
</html>
"""


def build_html(out: Path) -> None:
    (out / "data").mkdir(parents=True, exist_ok=True)
    shutil.copy(STATIC_DIR / "map.js", out / "map.js")
    shutil.copy(STATIC_DIR / "map.css", out / "map.css")
    shutil.copy(WEB_PRECINCTS, out / "data" / WEB_PRECINCTS.name)
    for key in ("county", "districts", "municipalities"):
        src = PRECINCT_DIR / LAYER_FILES[key]
        if src.exists():
            shutil.copy(src, out / "data" / src.name)
    (out / "data" / "locations.geojson").write_text(json.dumps(locations_geojson(), separators=(",", ":")), encoding="utf-8")
    (out / "index.html").write_text(HTML.format(css=CDN_CSS, js=CDN_JS, date=dt.date.today().isoformat()), encoding="utf-8")


def _patch(geom, **kw):
    """shapely (Multi)Polygon -> matplotlib PathPatch with holes."""
    polys = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
    verts, codes = [], []
    for poly in polys:
        for ring in [poly.exterior, *poly.interiors]:
            pts = list(ring.coords)
            verts.extend(pts); codes.extend([MPath.MOVETO] + [MPath.LINETO] * (len(pts) - 2) + [MPath.CLOSEPOLY])
    return PathPatch(MPath(verts, codes), **kw)


def build_wall_map(out: Path) -> Path:
    fc = json.loads(WEB_PRECINCTS.read_text(encoding="utf-8"))
    with open(POLLING_PLACES, newline="", encoding="utf-8") as f:
        places = sorted(csv.DictReader(f), key=lambda r: int(r["precinct"]))
    county = PRECINCT_DIR / LAYER_FILES["county"]
    munis = PRECINCT_DIR / LAYER_FILES["municipalities"]
    lakes = PRECINCT_DIR / LAYER_FILES["lakes"]
    roads = PRECINCT_DIR / LAYER_FILES["roads"]

    fig = plt.figure(figsize=(8.5, 14))
    ax = fig.add_axes([0.03, 0.415, 0.94, 0.50])
    tab = fig.add_axes([0.06, 0.035, 0.88, 0.345]); tab.axis("off")

    import math

    def draw(axis, label_fs, road_lw, muni_labels=True, min_lake_area=2e-5):
        axis.set_aspect(1 / math.cos(math.radians(34.95)))
        axis.axis("off")
        if lakes.exists():
            for f in json.loads(lakes.read_text())["features"]:
                g = shape(f["geometry"])
                if g.geom_type in ("Polygon", "MultiPolygon") and g.area > min_lake_area:
                    axis.add_patch(_patch(g, facecolor="#cfe0ee", edgecolor="#9fbdd6", linewidth=0.4, zorder=2.5))
        for f in fc["features"]:
            g = shape(f["geometry"]); p = f["properties"]
            axis.add_patch(_patch(g, facecolor="#fbf4ee" if p["comm"] == 1 else "#f3ede8" if p["comm"] == 2 else "#ece6e1",
                                  edgecolor="#a61e2b", linewidth=0.9, zorder=2))
            axis.text(p["label_lon"], p["label_lat"], str(p["precinct"]), ha="center", va="center", fontsize=label_fs, fontweight="bold",
                      color="#1c1a19", zorder=8, clip_on=True, bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.8))
        if roads.exists():
            for f in json.loads(roads.read_text())["features"]:
                g = shape(f["geometry"])
                for ln in (list(g.geoms) if g.geom_type == "MultiLineString" else [g]):
                    xs, ys = zip(*ln.coords); axis.plot(xs, ys, color="#8a8580", linewidth=road_lw, zorder=3, solid_capstyle="round")
        if munis.exists():
            for f in json.loads(munis.read_text())["features"]:
                g = shape(f["geometry"])
                axis.add_patch(_patch(g, facecolor="#ffd35c", alpha=0.25, edgecolor="#8a6d00", linewidth=0.5, zorder=4))
                if muni_labels:
                    c = g.representative_point()
                    axis.text(c.x, c.y + 0.012, f["properties"].get("CITYNAME", ""), ha="center", va="bottom", fontsize=6.5, style="italic", color="#5a4a00", zorder=6, clip_on=True)
        if county.exists():
            for f in json.loads(county.read_text())["features"]:
                axis.add_patch(_patch(shape(f["geometry"]), facecolor="none", edgecolor="#1c1a19", linewidth=1.6, linestyle=(0, (5, 3)), zorder=7))

    draw(ax, 8.5, 0.5)
    bounds = [shape(f["geometry"]).bounds for f in fc["features"]]
    ax.set_xlim(min(b[0] for b in bounds) - 0.02, max(b[2] for b in bounds) + 0.02)
    ax.set_ylim(min(b[1] for b in bounds) - 0.02, max(b[3] for b in bounds) + 0.02)

    # McAlester inset: the small urban precincts are unreadable at county scale
    urban = [f for f in fc["features"] if f["properties"]["precinct"] in (1, 3, 4, 5, 6, 7, 8, 11, 14, 54, 55, 41)]
    ub = [shape(f["geometry"]).bounds for f in urban]
    x0, y0, x1, y1 = min(b[0] for b in ub), min(b[1] for b in ub), max(b[2] for b in ub), max(b[3] for b in ub)
    ins = fig.add_axes([0.645, 0.425, 0.325, 0.175])
    draw(ins, 8, 0.8, muni_labels=False, min_lake_area=0)
    ins.set_xlim(x0 - 0.01, x1 + 0.01); ins.set_ylim(y0 - 0.01, y1 + 0.01)
    ins.axis("on"); ins.set_xticks([]); ins.set_yticks([])
    for sp in ins.spines.values(): sp.set_edgecolor("#1c1a19"); sp.set_linewidth(1.2)
    ins.set_facecolor("white")
    ins.set_title("McAlester / Krebs detail", fontsize=8.5, fontweight="bold", loc="left", pad=3)
    from matplotlib.patches import Rectangle
    ax.add_patch(Rectangle((x0 - 0.01, y0 - 0.01), (x1 - x0) + 0.02, (y1 - y0) + 0.02, fill=False, edgecolor="#1c1a19", linewidth=1.0, zorder=9))

    fig.text(0.06, 0.972, "Pittsburg County, Oklahoma — Voting Precincts", fontsize=16, fontweight="bold", color="#1c1a19")
    fig.text(0.06, 0.955, "County referendum — Emerald ProjectCo data center tax abatement · Petition Captain wall map (legal 8.5 × 14 in)",
             fontsize=9, color="#6b625f")
    fig.text(0.06, 0.012, f"Precinct boundaries: OU Center for Spatial Analysis (Oklahoma State Election Board mapping contractor), 2020 precincts. "
             f"Polling places: Pittsburg County Election Board. Shading = commissioner district 1/2/3. Built {dt.date.today().isoformat()}.",
             fontsize=7, color="#6b625f")

    # polling place table — two columns below the map
    tab.text(0.5, 1.0, "Precinct · Polling place · City", fontsize=10.5, fontweight="bold", va="top", ha="center",
             color="#1c1a19", transform=tab.transAxes)
    half = (len(places) + 1) // 2
    step = 0.90 / half
    cols = [(0.00, 0.055, 0.40), (0.53, 0.585, 0.93)]
    for i, r in enumerate(places):
        col, row = divmod(i, half) if False else (i // half, i % half)
        x_p, x_n, x_c = cols[col]
        y = 0.925 - (row + 1) * step
        if row % 2 == 0:
            tab.axhspan(y - step / 2, y + step / 2, xmin=x_p, xmax=x_c + 0.07, color="#f1eeeb", zorder=0)
        tab.text(x_p, y, r["precinct"], fontsize=8.6, fontweight="bold", va="center", color="#a61e2b", transform=tab.transAxes)
        name = r["polling_place"]
        if len(name) > 36: name = name[:35] + "…"
        tab.text(x_n, y, name, fontsize=8.6, va="center", transform=tab.transAxes)
        tab.text(x_c, y, r["city"], fontsize=8.6, va="center", color="#6b625f", transform=tab.transAxes)
    pdf = out / "pittsburg-precincts-legal.pdf"
    fig.savefig(pdf, format="pdf")
    plt.close(fig)
    return pdf


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="output/map")
    a = ap.parse_args(argv)
    out = Path(a.out) if Path(a.out).is_absolute() else ROOT / a.out
    out.mkdir(parents=True, exist_ok=True)
    build_html(out)
    pdf = build_wall_map(out)
    print(f"wrote {out / 'index.html'}")
    print(f"wrote {pdf} ({pdf.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
