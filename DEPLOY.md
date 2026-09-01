# Deploying petition.mcalester.net on Dokku

The app is a FastAPI service with a Postgres database. It is deployed from this repository with a
Dockerfile (`Dockerfile` at the root). Everything below runs on the Dokku host as a user with
`dokku` rights; replace `<host>` with the server name.

## 1. Create the app and the database
```sh
dokku apps:create petition
dokku postgres:create petition-db
dokku postgres:link petition-db petition          # sets DATABASE_URL (postgres://…); the app rewrites it for SQLAlchemy
```

## 2. Domains — canonical host + every misspelling
```sh
dokku domains:set petition petition.mcalester.net
dokku domains:add petition petiton.mcalester.net pettition.mcalester.net petitions.mcalester.net   # add each misspelling
```
Only `petition.mcalester.net` serves pages. A request that arrives at any other host name — a
misspelled domain you attached above, the server's bare IP, anything — gets a **301 redirect to
`https://petition.mcalester.net` with the same path and query string** (middleware in `app/main.py`).
`/healthz` is exempt so Dokku's zero-downtime checks work on any host.

## 3. Config
```sh
dokku config:set petition \
  CANONICAL_HOST=petition.mcalester.net \
  SECRET_KEY="$(openssl rand -hex 32)" \
  ADMIN_USER=captain \
  ADMIN_PASSWORD='<at least 10 characters>' \
  FORCE_HTTPS=1
```
- `SECRET_KEY` signs the admin session cookie. Rotating it signs everyone out.
- `ADMIN_USER` / `ADMIN_PASSWORD` create the first admin only if no users exist (safe to leave set).
- Optional: `EXTRA_ALLOWED_HOSTS=staging.example.org` to allow another host without redirecting.
- `GA_MEASUREMENT_ID` — Google tag on public pages only (default `G-3ECCW6ESQR`); set it to an empty string to disable analytics (local dev/tests).

## 4. TLS and ports
```sh
dokku letsencrypt:set petition email you@example.org
dokku ports:set petition http:80:5000
dokku letsencrypt:enable petition        # adds https:443:5000
dokku letsencrypt:cron-job --add
```
Let's Encrypt will request a certificate for every domain attached in step 2, so the misspellings
redirect over https without browser warnings.

## 5. Deploy
```sh
git remote add dokku dokku@<host>:petition
git push dokku main
```
`app.json` runs `python -m app.seed` after every deploy (idempotent: settings defaults where
missing, contacts/locations/events from `data/*.yaml`, the Filing-QA checklist, the first admin
user). `CHECKS` makes Dokku wait for `/healthz` before switching traffic.

## 6. One-time: load the existing tracker
Upload `Petition Captain Master Tracker.xlsx` in **Admin → Import / Export**, or from the host:
```sh
dokku enter petition web python -m toolkit.xlsx.import_tracker "/path/inside/container/tracker.xlsx"
```
(copy the file in with `dokku storage:mount` or `docker cp` first).

## 7. Backups
```sh
dokku postgres:export petition-db > petition-db-$(date +%F).dump     # nightly via cron
dokku postgres:import petition-db < petition-db-2026-09-01.dump      # restore
```
The database holds no signer names, addresses or birth dates — counts and statuses only — but it is
the campaign's system of record, so back it up daily during circulation.

## 8. Local development
```sh
. .venv/bin/activate
python -m app.seed --admin-user captain --admin-password 'local-dev-password'
make app-dev            # http://localhost:8000  (SQLite at output/dev.db unless DATABASE_URL is set)
```
To test against Postgres locally: `export DATABASE_URL=postgres://user:pw@localhost:5432/petition`.

## Useful
```sh
dokku logs petition -t
dokku run petition python -m app.seed --admin-user captain --admin-password '…'   # add a first admin later
dokku config:set petition FORCE_HTTPS=0     # only if TLS terminates somewhere odd
```
