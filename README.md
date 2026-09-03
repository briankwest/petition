# Pittsburg County Referendum Toolkit

Documents, tracking, map and website for a county referendum petition under the Oklahoma
Local Development Act (62 O.S. § 868) on the proposed Emerald ProjectCo data center tax
abatement. **Status: the Board of County Commissioners tabled the resolution — no adoption
date exists, so every date and the registered-voter count are placeholders.** Nothing may be
circulated until the resolution is adopted and a true copy of the petition is filed with the
Secretary of the Pittsburg County Election Board.

Not legal advice. Every legal instrument goes to an Oklahoma election-law attorney and the
County Election Board before filing or printing. See `PLAN.md` for the full plan and the
quoted statutes; `reference/statutes/` holds the verbatim text.

## Layout

| Path | What |
| --- | --- |
| `config/petition.yaml` | Single source of truth for documents (county, measure, dates, gist, ballot title, layout). `null` = placeholder. |
| `measure/adopted-resolution.md` | Exact adopted text of the measure (placeholder until adopted). |
| `measure/attachments/*.pdf` | Offline builds only: exhibit PDFs reproduced inside the pamphlet (sorted by filename). Online builds use the PDFs uploaded on admin → Petition. |
| `reference/statutes/` | Verbatim Oklahoma statutes with source URLs and retrieval dates. |
| `reference/source-docs/` | The original five Google-Docs exports (unchanged). |
| `toolkit/` | Python package: `config`, `statutes`, `docs` (WeasyPrint PDFs + checks), `xlsx` (export/import), `geo` (precincts, map, lookup), `freeze`. |
| `app/` | FastAPI site + Petition Captain admin (`petition.mcalester.net`, Dokku + Postgres). The database is the system of record for the Petition Master list. |
| `app/market.py` | Live IREN quote for the `/iren` dossier: Nasdaq's public feed (Yahoo fallback), cached in `market_quotes`. Cache only — never part of the petition record. |
| `data/` | Precinct GeoJSON (38 precincts, OU CSA / State Election Board), polling places, seed YAML for locations/events/contacts. |
| `output/` | Generated artifacts (git-ignored except `output/filed/`). |

## Setup

```sh
make venv            # python3 -m venv .venv && pip install -e ".[dev]"   (needs Homebrew pango for WeasyPrint)
. .venv/bin/activate
make test
```

## Everyday commands

```sh
make docs            # render all documents (draft, legal size) -> output/docs
make docs-db         # same, but from the DATABASE (admin-entered data): DATABASE_URL=... make docs-db
make check-docs      # statutory + layout checks on the PDFs
make xlsx            # export the Petition Master workbook from the database
make xlsx-import     # one-time import of "Petition Captain Master Tracker.xlsx" into the database
make map             # standalone interactive map + legal-size wall map -> output/map
make app-dev         # run the site locally on :8000 (SQLite unless DATABASE_URL is set)
make seed            # seed settings/contacts/locations/QA tasks (+ admin user from ADMIN_USER/ADMIN_PASSWORD)
.venv/bin/python -m app.seed --pamphlets --polling-places   # pre-create the print run + candidate venues
make check           # everything
make final           # filing build — refuses while any placeholder remains
make freeze          # hash + tag the filed pamphlet
```

Deployment to Dokku: see `DEPLOY.md`.

### The live IREN quote on `/iren`

The dossier opens with a live price panel for **Nasdaq: IREN**, fed by Nasdaq's own public
quote API (no key, no account) with Yahoo Finance as a fallback. `app/market.py` caches the
quote in the `market_quotes` table for five minutes and a year of daily closes for six hours,
so the page itself never waits on the market feed: it renders the last figure we got and
`/api/quote.json` refreshes it while the page is open. If both feeds go quiet the panel says
so and links to Nasdaq rather than showing a stale number as current.

- Hide the panel: admin → Settings → **Show the live IREN quote on /iren**.
- Turn the fetching off entirely (tests do this): `MARKET_DATA=off`.
- Check it after a deploy: `curl -s https://petition.mcalester.net/api/quote.json | head -c 200`.

Nothing about the quote touches the petition documents — it is not part of the dossier's data
cut-off and is labelled as such on the page.

## Rules that never change

- No signatures before the true copy is filed. Only the frozen, filed pamphlet is printed.
- No signer names, addresses or birth dates in the database, the workbook export, or the website — tracking is at pamphlet/sheet level. Paper is the only record of signers.
- Statute text is quoted from `reference/statutes/`, never from memory.
