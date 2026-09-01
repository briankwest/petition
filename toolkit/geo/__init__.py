"""Precinct GIS data, address→precinct lookup, and map builds for Pittsburg County."""
from pathlib import Path
from .. import ROOT

DATA_DIR = ROOT / "data"
PRECINCT_DIR = DATA_DIR / "precincts"
RAW_PRECINCTS = PRECINCT_DIR / "pittsburg_pct2020.geojson"
WEB_PRECINCTS = PRECINCT_DIR / "pittsburg_web.geojson"
POLLING_PLACES = DATA_DIR / "polling_places.csv"
SIGNING_LOCATIONS = DATA_DIR / "signing_locations.yaml"
STATIC_DIR = ROOT / "app" / "static"

# Plausible bounding box for Pittsburg County, OK (lat, lon)
# Precincts span 34.59–35.30 N, 96.09–95.45 W; keep a small margin.
COUNTY_BBOX = {"lat_min": 34.55, "lat_max": 35.35, "lon_min": -96.15, "lon_max": -95.30}
