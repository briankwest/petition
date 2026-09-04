# Pittsburg County referendum toolkit. Always run inside the venv: `. .venv/bin/activate`.
PY ?= .venv/bin/python
TRACKER ?= Petition Captain Master Tracker.xlsx

.PHONY: venv docs docs-final check-docs xlsx xlsx-import check-xlsx fetch-precincts geocode icons map check-geo test check final freeze app-dev seed clean tldr-pdf letters
CHROME ?= /Applications/Google Chrome.app/Contents/MacOS/Google Chrome
TLDR_URL ?= https://petition.mcalester.net/tldr?print=1

venv:
	python3 -m venv .venv && .venv/bin/pip install -U pip && .venv/bin/pip install -e ".[dev]"

docs:            ## render every document (draft mode, placeholders allowed) -> output/docs
	$(PY) -m toolkit.docs.build --out output/docs
docs-db:         ## render from the DATABASE (admin-entered data): DATABASE_URL=... make docs-db
	$(PY) -m toolkit.docs.build --out output/docs --from-db
docs-final:      ## render for filing: refuses while any placeholder remains -> output/final
	$(PY) -m toolkit.docs.build --final --out output/final
check-docs:      ## statutory + layout checks on the rendered PDFs
	$(PY) -m toolkit.docs.check output/docs

xlsx:            ## export the Petition Master workbook from the database (blank template if the DB is empty)
	$(PY) -m toolkit.xlsx.export --out output/xlsx/petition-master.xlsx
xlsx-import:     ## one-time: load the existing tracker into the database
	$(PY) -m toolkit.xlsx.import_tracker "$(TRACKER)"
check-xlsx:
	$(PY) -m toolkit.xlsx.check output/xlsx/petition-master.xlsx

fetch-precincts: ## refresh precinct/county/district GeoJSON from the OU CSA ArcGIS service
	$(PY) -m toolkit.geo.fetch
geocode:         ## fill lat/lon for signing locations via the Census geocoder
	$(PY) -m toolkit.geo.geocode
icons:           ## regenerate favicon set + Open Graph share image (app/static)
	$(PY) -m toolkit.branding
map:             ## standalone interactive map + legal-size wall map -> output/map
	$(PY) -m toolkit.geo.build_map --out output/map
check-geo:
	$(PY) -m toolkit.geo.check

test:
	$(PY) -m pytest -q
check: check-docs check-xlsx check-geo test

final: docs-final ## filing build: strict checks
	$(PY) -m toolkit.docs.check output/final --final
tldr-pdf:        ## re-render app/static/tldr.pdf from the live one-page sheet (Chrome, Letter, exact); rerun when the numbers change, then deploy
	"$(CHROME)" --headless=new --disable-gpu --no-pdf-header-footer --virtual-time-budget=10000 --print-to-pdf=app/static/tldr.pdf "$(TLDR_URL)"
	@$(PY) -c "import re,pathlib; b=pathlib.Path('app/static/tldr.pdf').read_bytes(); n=len(re.findall(rb'/Type\s*/Page[^s]', b)); print('app/static/tldr.pdf:', n, 'page(s),', len(b), 'bytes'); raise SystemExit(0 if n==1 else 1)"

letters:         ## records-request letters -> output/letters (PDF per letter + docupost.csv); sender from config/sender.local.yaml
	$(PY) -m toolkit.letters.build --out output/letters

freeze:          ## hash + tag the filed pamphlet; later builds must match
	$(PY) -m toolkit.freeze output/final/01-petition-pamphlet.pdf

app-dev:         ## run the site locally (SQLite unless DATABASE_URL is set); fixed dev SECRET_KEY so restarts keep you signed in
	SECRET_KEY=$${SECRET_KEY:-dev-only-not-secret-change-in-dokku} $(PY) -m uvicorn app.main:app --reload --port 8000
seed:            ## load data/*.yaml + config into the database
	$(PY) -m app.seed

clean:
	rm -rf output/docs output/final output/xlsx output/map
