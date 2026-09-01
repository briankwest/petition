"""Fill lat/lon (and precinct) for entries in data/signing_locations.yaml that lack them,
using the Census Bureau geocoder. Existing coordinates are kept. Header comments are preserved.

    python -m toolkit.geo.geocode [--force]
"""
from __future__ import annotations
import argparse, sys
import yaml
from . import SIGNING_LOCATIONS
from .lookup import geocode, PrecinctIndex


def load_locations(path=SIGNING_LOCATIONS) -> tuple[str, dict]:
    text = path.read_text(encoding="utf-8")
    header = "".join(line for line in text.splitlines(keepends=True) if line.startswith("#"))
    return header, (yaml.safe_load(text) or {"locations": []})


def format_address(loc: dict) -> str:
    parts = [loc.get("address"), loc.get("city"), "OK", str(loc.get("zip") or "")]
    return ", ".join(p for p in parts if p)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true", help="re-geocode even entries that already have lat/lon")
    a = ap.parse_args(argv)
    header, data = load_locations()
    idx = PrecinctIndex()
    changed = 0
    for loc in data.get("locations") or []:
        if not a.force and loc.get("lat") is not None and loc.get("lon") is not None:
            if not loc.get("precinct"):
                p = idx.find(loc["lat"], loc["lon"])
                if p:
                    loc["precinct"] = p["precinct"]; changed += 1
            continue
        addr = format_address(loc)
        g = geocode(addr)
        if not g:
            print(f"  ! {loc.get('id')}: no match for {addr!r}")
            continue
        loc["lat"], loc["lon"] = round(g["lat"], 6), round(g["lon"], 6)
        p = idx.find(g["lat"], g["lon"])
        loc["precinct"] = p["precinct"] if p else None
        print(f"  ✓ {loc.get('id')}: {g['matched_address']} -> ({loc['lat']}, {loc['lon']}) precinct {loc['precinct']}")
        changed += 1
    if changed:
        body = yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100)
        SIGNING_LOCATIONS.write_text(header + body, encoding="utf-8")
        print(f"wrote {SIGNING_LOCATIONS} ({changed} updated)")
    else:
        print("nothing to geocode")
    return 0


if __name__ == "__main__":
    sys.exit(main())
