# Data sources (verified 2026-09-01)

| File | Source | Notes |
| --- | --- | --- |
| `precincts/pittsburg_pct2020.geojson` | OU Center for Spatial Analysis ArcGIS feature service `Pittsburg_County_Data/FeatureServer/10` (`pct2020_121`), https://services7.arcgis.com/cpyRdAfuizCFzBhp/arcgis/rest/services/Pittsburg_County_Data/FeatureServer | 38 precinct polygons, EPSG:4326. The State Election Board contracts CSA for its maps (https://oklahoma.gov/elections/candidates/district-and-precinct-maps.html). Same service also has county boundary (layer 0), commissioner districts (`comm2020_121`, layer 2), municipalities (`muni2020_121`, layer 8), roads (15), lakes (7). Statewide equivalent: `Voter_Precincts_2020/FeatureServer/0`. |
| `polling_places.csv` | Pittsburg County Election Board, https://pittsburg.okcounties.org/departments/election-board/precincts | 38 precincts; numbers match the GIS layer exactly. Re-verify before printing anything. |
| (fallback) | U.S. Census TIGER/Line 2020 VTDs, https://www2.census.gov/geo/tiger/TIGER2020PL/STATE/40_OKLAHOMA/40/tl_2020_40_vtd20.zip | Filter `COUNTYFP20 = 121`. Use only if the CSA service is unavailable. |

Pittsburg County Election Board: 1609 N. Strong Blvd. STE 200, McAlester, OK 74501 · 918-423-3877 · fax 918-423-7088 · pittsburgcounty@elections.ok.gov · Secretary Tonya Barnes · Mon–Fri 8:00 a.m.–4:00 p.m. (https://pittsburg.okcounties.org/offices/election-board)

OK Voter Portal (registration lookup; requires name + date of birth): https://okvoterportal.okelections.gov/

## Derived files (built by `python -m toolkit.geo.fetch --all`, 2026-09-01)

| File | What | Size |
| --- | --- | --- |
| `precincts/pittsburg_web.geojson` | 38 precincts, shared-edge simplified (snap 1e-5°, tolerance 0.0005°, zero overlaps), props: precinct, pct_ceb, polling_place, address, city, pop2020, vap2020, comm, label_lat/label_lon | ~52 KB |
| `precincts/county.geojson` | County boundary (layer 0) | 75 KB |
| `precincts/commissioner_districts.geojson` | 3 commissioner districts 2020 (layer 2, prop `DISTRICT`) | 218 KB |
| `precincts/municipalities.geojson` | 14 municipalities 2020 (layer 8, prop `CITYNAME`) | 74 KB |
| `precincts/lakes.geojson` | 49 water polygons (layer 7) | 707 KB |
| `precincts/roads.geojson` | 827 highway-class centerlines only (US 69/270, SH 31/63/113/9E, Indian Nation Tpke, George Nigh Expy) filtered from the 8,375-segment PSAP layer 15; `--full-roads` keeps everything (~17 MB) | 455 KB |

Geocoding (`toolkit.geo.lookup.geocode`): U.S. Census Bureau geocoder first (no key); OpenStreetMap Nominatim as fallback when Census has no match or returns the wrong street directional (e.g. Census maps "801 N 9th St, McAlester" to S 9th St). Nominatim usage policy: ≤ 1 request/s, identified User-Agent — fallback only, never bulk.

| `../reference/source-docs/publication_for_public_hearings_1870.pdf` | Pittsburg County legal advertisement, filed May 18, 2026 (County Clerk) | Official pre-adoption wording: "Emerald ProjectCo Data Center Project Economic Development Project Plan"; "Incentive District No. 1 / No. 2, Pittsburg County" ("TID Districts"); 62 O.S. § 850 et seq.; hearings June 8 + June 22, 2026, Southeast Expo Center. See NOTES-public-hearing-notice.md. |
