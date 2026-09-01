import json, socket
import pytest
from toolkit.geo import WEB_PRECINCTS, RAW_PRECINCTS
from toolkit.geo.lookup import PrecinctIndex, nearest, haversine_mi
from toolkit.geo import check as geocheck


def _online() -> bool:
    try:
        socket.create_connection(("geocoding.geo.census.gov", 443), timeout=3).close()
        return True
    except OSError:
        return False


@pytest.fixture(scope="module")
def idx():
    return PrecinctIndex()


def test_files_exist():
    assert RAW_PRECINCTS.exists() and WEB_PRECINCTS.exists()
    assert len(json.loads(WEB_PRECINCTS.read_text())["features"]) == 38


def test_find_mcalester_point(idx):
    # McAlester (downtown-ish). Note: the directive's example point (35.933, -95.769) is near Tulsa; McAlester is ~34.93 N.
    p = idx.find(34.933, -95.769)
    assert p is not None and 1 <= p["precinct"] <= 55 and p["polling_place"]


def test_find_outside_county(idx):
    assert idx.find(36.154, -95.993) is None      # Tulsa
    assert idx.find(35.933, -95.769) is None      # Okmulgee/Muskogee area, north of the county


def test_every_label_point_is_inside_its_precinct(idx):
    for props in idx.props:
        hit = idx.find(props["label_lat"], props["label_lon"])
        assert hit and hit["precinct"] == props["precinct"], props["precinct"]


def test_nearest_ordering():
    pts = [{"name": "far", "lat": 35.2, "lon": -95.5}, {"name": "near", "lat": 34.94, "lon": -95.77}, {"name": "nocoords"}]
    out = nearest(34.93, -95.77, pts)
    assert [p["name"] for p in out] == ["near", "far"] and out[0]["distance_mi"] < out[1]["distance_mi"]
    assert abs(haversine_mi(34.93, -95.77, 34.93, -95.77)) < 1e-9


def test_check_passes():
    assert geocheck.run(verbose=False) == []


@pytest.mark.skipif(not _online(), reason="network unavailable")
def test_geocode_and_lookup(idx):
    r = idx.lookup_address("1609 N Strong Blvd, McAlester, OK 74501", points=[{"name": "x", "lat": 34.95, "lon": -95.76}])
    assert r["lat"] and r["precinct"] and r["precinct"]["precinct"] and r["nearest"][0]["distance_mi"] >= 0
