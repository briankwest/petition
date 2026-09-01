"""Integrity checks on the precinct data. Exit 1 on any failure.

    python -m toolkit.geo.check
"""
from __future__ import annotations
import csv, json, sys
from itertools import combinations
from shapely.geometry import shape
from . import RAW_PRECINCTS, WEB_PRECINCTS, POLLING_PLACES, COUNTY_BBOX


def run(verbose: bool = True) -> list[str]:
    errors: list[str] = []
    say = print if verbose else (lambda *a, **k: None)
    with open(POLLING_PLACES, newline="", encoding="utf-8") as f:
        pp = {int(r["precinct"]): r for r in csv.DictReader(f)}
    say(f"polling_places.csv: {len(pp)} precincts")

    for path, numkey in ((RAW_PRECINCTS, "precinct_num"), (WEB_PRECINCTS, "precinct")):
        if not path.exists():
            errors.append(f"{path.name}: missing"); continue
        fc = json.loads(path.read_text(encoding="utf-8"))
        feats = fc.get("features", [])
        say(f"{path.name}: {len(feats)} features, {path.stat().st_size:,} bytes")
        if len(feats) != 38:
            errors.append(f"{path.name}: expected 38 features, found {len(feats)}")
        nums = set()
        geoms = {}
        for f in feats:
            n = f["properties"].get(numkey)
            try:
                n = int(n)
            except (TypeError, ValueError):
                errors.append(f"{path.name}: feature without {numkey}: {f['properties']}"); continue
            if n in nums:
                errors.append(f"{path.name}: duplicate precinct {n}")
            nums.add(n)
            g = shape(f["geometry"])
            if g.is_empty or not g.is_valid or g.geom_type not in ("Polygon", "MultiPolygon"):
                errors.append(f"{path.name}: precinct {n} geometry invalid/empty ({g.geom_type})")
            geoms[n] = g
            minx, miny, maxx, maxy = g.bounds
            if not (COUNTY_BBOX["lon_min"] <= minx and maxx <= COUNTY_BBOX["lon_max"] and COUNTY_BBOX["lat_min"] <= miny and maxy <= COUNTY_BBOX["lat_max"]):
                errors.append(f"{path.name}: precinct {n} bounds {g.bounds} outside county bbox")
            if path is WEB_PRECINCTS and not f["properties"].get("polling_place"):
                errors.append(f"{path.name}: precinct {n} has no polling_place")
        if nums != set(pp):
            errors.append(f"{path.name}: precinct set differs from polling_places.csv: only-in-geo={sorted(nums - set(pp))} only-in-csv={sorted(set(pp) - nums)}")
        for a, b in combinations(sorted(geoms), 2):
            ga, gb = geoms[a], geoms[b]
            if ga.intersects(gb):
                ov = ga.intersection(gb).area
                smaller = min(ga.area, gb.area)
                if smaller and ov / smaller >= 0.005:
                    errors.append(f"{path.name}: precincts {a} and {b} overlap {ov/smaller:.2%} of the smaller")
        if path is WEB_PRECINCTS and path.stat().st_size > 250_000:
            errors.append(f"{path.name}: {path.stat().st_size:,} bytes exceeds 250 KB")
    return errors


def main() -> int:
    errors = run()
    if errors:
        print("\nFAILED:")
        for e in errors:
            print(" -", e)
        return 1
    print("\nOK: precinct data passes all checks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
