# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A toolkit for a county referendum petition in **Pittsburg County, Oklahoma** against an 85%
property-tax abatement for the Emerald ProjectCo / IREN data center (Oklahoma Local Development
Act, 62 O.S. § 868). It produces the legal-size petition pamphlet and field documents, runs the
Petition Captain's tracking (web admin + Postgres, XLSX export), and serves the public site with
the precinct map at `petition.mcalester.net`. `PLAN.md` is the plan; `README.md` the user guide.

**Current legal posture:** the Board of County Commissioners **tabled** the resolution. There is
no adoption date, no filing deadline, no election date, and no verified registered-voter count.
All of these are `null` placeholders in `config/petition.yaml` and render as bracketed
`[… — TBD]` text. Never invent a date or a count. Never reintroduce "June 22" / "July 22".

## Commands

Always activate the venv first: `. .venv/bin/activate` (Python 3.14; WeasyPrint needs Homebrew pango).

- `make test` — pytest; single file: `.venv/bin/python -m pytest tests/test_docs.py -q`
- `make docs` / `make check-docs` — render PDFs to `output/docs` and run the statutory checks
- `make final` — filing build; fails while `Petition.placeholders` is non-empty
- `make xlsx` / `make xlsx-import` — export workbook from DB / import the old tracker
- `make map`, `make fetch-precincts`, `make geocode`, `make check-geo`
- `make app-dev` (SQLite at `output/dev.db` unless `DATABASE_URL`), `make seed`
- `make check` — all checks; `make freeze` — hash the filed pamphlet

## Architecture (read these before changing anything)

- `toolkit/config.py` — loads `config/petition.yaml` into `Petition`; derived fields
  (`filing_deadline` = adoption + 30 days, `legal_minimum` = ceil(10% × registered voters),
  `placeholders`, `is_final_ready`, `fmt.*`). `PLACEHOLDER_RE` is the one definition of
  "not ready to file". Every generator reads from here — do not hard-code county facts elsewhere.
- `toolkit/statutes.py` — the only way templates and checkers get statutory wording
  (`warning_sentence()`, `affidavit(county)`, `signer_attestation()`, `exclusions()` = E1–E8).
  Text comes from `reference/statutes/*.txt` (verbatim, dated). Templates and checks must both
  use these helpers so drift is caught.
- `toolkit/docs/` — Jinja2 + WeasyPrint. Legal size only (612×1008 pt / 1008×612 pt). The
  pamphlet is one PDF: cover(Warning) → petition → exact measure (padded to even) → proponents →
  [signature sheet, affidavit] × N with sheets on odd pages. `check.py` is the contract.
  On the server, documents render from `app.petition.from_db(db)` (admin-entered data; YAML is
  seed-only): admin Documents → Generate stores builds in Postgres (`DocumentBuild`/`DocumentFile`,
  `app/docbuilder.py`); Freeze pins the filed pamphlet's `content_fingerprint` and locks
  `/admin/petition`; pamphlets print one at a time (Assign → Print stamped → Issue), refused
  unless the print matches the filed fingerprint.
- `app/models.py` — Petition Master data model (Setting, User, Circulator, Pamphlet, Sheet,
  Issue, Location, Event, Contact, QATask, RecordsLog). Status vocabularies mirror the captain's
  original tracker. **No signer PII columns exist and none may be added.**
- `app/settings.py` (`Settings(db)`: admin-editable dates/counts with config defaults) and
  `app/stats.py` (`signature_stats`) — the single source of live numbers for the site, admin and
  XLSX export.
- `app/` FastAPI: host-redirect middleware (anything but `CANONICAL_HOST` → 301 to
  `https://petition.mcalester.net`), public pages, `/admin` (session auth, CSRF), JSON APIs, seed.
  Deployed with `Dockerfile` on Dokku; Postgres via `DATABASE_URL` (scheme rewritten in `app/db.py`).
- `toolkit/xlsx/` — export (DB → workbook keeping the original tracker's sheet/column layout and
  live formulas) and import (old tracker → DB). `toolkit/geo/` — ArcGIS fetch, `PrecinctIndex`
  (point-in-polygon + Census geocoder), map builder, `app/static/map.js` (`initPetitionMap`).

## Invariants

- Legal instruments follow 34 O.S. §§ 1, 3, 6 and 62 O.S. § 868 as quoted in `reference/statutes/`;
  the ballot title is a separate document (≤150 words, § 868(D)); circulators must be registered
  Oklahoma voters (`Circulator.can_circulate` gates issuing a pamphlet).
- Keep the five statutory signer fields (legal first, legal last, ZIP, house #, birth MM/DD) on every
  sheet; 4 of 5 must match the voter file (34 O.S. § 1(B)).
- After filing, the pamphlet PDF is frozen (`make freeze`); later builds must match its hash.
- Do not delete or rename files in `reference/source-docs/` (kept unchanged, including the
  `Notary Checklilst.md` spelling).
- Don't commit or push unless asked; Dokku deploys from `main` (`DEPLOY.md`).
