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
| `reference/statutes/` | Verbatim Oklahoma statutes with source URLs and retrieval dates. |
| `reference/source-docs/` | The original five Google-Docs exports (unchanged). |
| `toolkit/` | Python package: `config`, `statutes`, `docs` (WeasyPrint PDFs + checks), `xlsx` (export/import), `geo` (precincts, map, lookup), `freeze`. |
| `app/` | FastAPI site + Petition Captain admin (`petition.mcalester.net`, Dokku + Postgres). The database is the system of record for the Petition Master list. |
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
make check-docs      # statutory + layout checks on the PDFs
make xlsx            # export the Petition Master workbook from the database
make xlsx-import     # one-time import of "Petition Captain Master Tracker.xlsx" into the database
make map             # standalone interactive map + legal-size wall map -> output/map
make app-dev         # run the site locally on :8000 (SQLite unless DATABASE_URL is set)
make seed            # seed settings/contacts/locations/QA tasks (+ admin user from ADMIN_USER/ADMIN_PASSWORD)
make check           # everything
make final           # filing build — refuses while any placeholder remains
make freeze          # hash + tag the filed pamphlet
```

Deployment to Dokku: see `DEPLOY.md`.

## Rules that never change

- No signatures before the true copy is filed. Only the frozen, filed pamphlet is printed.
- No signer names, addresses or birth dates in the database, the workbook export, or the website — tracking is at pamphlet/sheet level. Paper is the only record of signers.
- Statute text is quoted from `reference/statutes/`, never from memory.
