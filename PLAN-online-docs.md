# Plan: petition data + document generation in the admin

**Goal.** Everything the printed documents need (dates, resolution text, proponents, captain, layout) is entered once, in the admin, and the PDFs — pamphlet, ballot title, quick card, notary checklist, plans, training cards — are generated and previewed online from that data. The filing copy still gets frozen and hash-locked. `config/petition.yaml` becomes the seed for constants (county, statutes, layout defaults), not the place you type dates.

## 0. Today
- Two sources: `config/petition.yaml` → PDFs (rendered at deploy, in the Docker image); admin **Settings** → site/dashboard (adoption date, election date, voter count, captain). Dates are typed twice; captain/proponents/resolution text only exist in the YAML, so the cards print blanks.
- Placeholders outstanding: resolution number, title, exact adopted text, adoption date, election date, proponents (1–3), captain name/phone.

## 1. One source of truth: the database
- `toolkit.config.Petition` stays the object every renderer consumes. Add `app.petition.from_db(db)` that builds it from **config defaults overlaid with Settings rows** (same keys as today plus the new ones below). No schema migration: new values live in the existing key/value `settings` table (Text column holds the resolution text; proponents stored as JSON).
- New admin page **Petition** (`/admin/petition`), admin role only:
  - Measure: resolution number, exact title, adoption date, **exact adopted text** (large Markdown editor + optional upload of the certified .txt/.md; exhibits appended), districts/project name.
  - Election date (next general county election).
  - Proponents of record: up to three rows — name, registration address, city, ZIP (§ 1 form).
  - Gist and ballot title with live word count (ballot title ≤ 150 words, § 868(D)) and the neutrality lint from `toolkit.docs.check`.
  - Captain name/phone (moves here from Settings; Settings keeps site-only items).
  - Layout: lines per sheet, sheets per pamphlet, duplex mode.
  - A **placeholder panel** listing what is still missing, identical to `Petition.placeholders`.
- Settings already used by the site (registered voters, overcollection, banner, flags) are unchanged.

## 2. Generate documents online
- **Documents** page gets **Generate (draft)** and, when no placeholders remain and checks pass, **Generate final**. A build runs `toolkit.docs.build.build_all(petition=from_db(db))` in a background thread (WeasyPrint is already in the image; ~30 s for all seven), then `toolkit.docs.check` on the result; the page polls status.
- **Storage**: Dokku containers are ephemeral, so builds are stored in Postgres — `document_builds` (id, kind draft/final, built_at, by, manifest JSON, check report, petition snapshot) and `document_files` (build_id, name, bytes, sha256). ~1 MB per build; keep the last 20 (drafts pruned first). Backups already cover the DB. The image-time build remains as the fallback when no DB build exists.
- Preview/download exactly as now, per build; a build history table with who/when/draft-or-final/checks.
- Per-volunteer training cards and a **"Cards for all cleared volunteers"** batch PDF render on demand from the same `from_db` Petition, so the captain's name and phone are always current.

## 3. Freeze and print control (the legal gate)
- **Freeze** (admin-only, confirm dialog): marks one *final* build as **FILED**, records the file-stamp date/time/office/receiver into the Records Log, stores the pamphlet SHA-256, and **locks the Petition page** (read-only). Unfreeze requires a reason and is logged; a new final build after unfreeze is a new filing.
- Any later build whose pamphlet hash differs from the filed hash is labeled **DIFFERS FROM FILED — do not print**. Print batches (Pamphlets → "Mark printed") record the build id + hash on each pamphlet (`Pamphlet.version_hash`).
- Public site shows "Filed on <date>" in the banner once frozen (optional flag).

## 4. Local workflow stays
- `make docs` keeps rendering from YAML for offline work; add `--from-db` (`DATABASE_URL=… make docs-db`) to render from a database. Tests cover both paths.

## 5. Work breakdown
| Phase | Scope | Est. |
| --- | --- | --- |
| A | `from_db` Petition; Petition admin page; captain prefill in all documents; placeholder panel | 2–3 h |
| B | Background build + Postgres storage + Documents page history/preview; batch training cards | 3 h |
| C | Freeze / lock / unfreeze-with-reason; hash comparison; print-batch hash; Records Log entry | 2 h |
| D | `--from-db` for `make docs`; tests; DEPLOY notes | 1 h |

## 6. Decisions to confirm
1. Store generated PDFs in **Postgres** (recommended; no server config, backed up) vs. a Dokku persistent mount.
2. **Who may freeze/unfreeze**: admin role only (recommended).
3. After freeze, edits are blocked unless explicitly unfrozen with a logged reason (recommended) — or fully immutable.
4. Keep `config/petition.yaml` as seed-only (recommended) — county constants and statute list stay in git; everything variable lives in the DB.

> **Decisions (2026-09-01):** Postgres storage; freeze/unfreeze admin-only with a logged reason; `config/petition.yaml` seed-only; pamphlets print **one at a time, only when assigned to a cleared circulator and the petition is frozen** — no bulk print packs.

## 7. Phase E — pre-numbered, pre-assigned pamphlet prints (DECIDED: one at a time)
- **What prints**: the pamphlet number large on the cover box and in every page header/footer ("Pamphlet P-017 · Sheet 3 of 5"), an **Issued to** line on the cover (volunteer name + Training ID, print batch), and the circulator's **printed name** on each affidavit's printed-name line. Signature, address, date and the notary block stay blank — they are completed at notarization by the person who actually circulated.
- **DECIDED — no bulk packs.** A pamphlet prints **one at a time**, only when it is *assigned and ready*: the petition is FROZEN (filed), the pamphlet has an assigned circulator, and that circulator is cleared (registration verified + trained). Flow per pamphlet: **Assign** (sets the circulator; status stays Ready to Print) → **Print** (renders that one stamped pamphlet; fingerprint-checked against the filed build; status → Printed, print recorded) → **Mark issued** when it is physically handed over. **Void & reprint** (reason required, logged) covers reassignment.
- **The rule — reassignment means reprint, never a cross-out.** An affidavit must be sworn by the person who circulated the sheet (34 O.S. § 6); a corrected name invites an E1 challenge that voids the whole sheet (§ 6.1(A)(1)). So if P-017 moves from one volunteer to another: reprint P-017 for the new person, void the old copy in the log, and destroy it. Because the number stays unique, tracking is unaffected.
- **Freeze compatibility**: stamping blanks does not change the petition. The freeze stores two values for the pamphlet: the byte hash of the master PDF and a **content fingerprint** of the invariant pages (cover text minus stamps, petition, measure, proponents, sheet/affidavit template text). Print packs must match the fingerprint; the byte hash applies only to the master. The checker already computes the fingerprint.
- **Data**: no new columns — `Pamphlet.issued_to`, `print_batch`, `version_hash` exist. Volunteer address is not stored (by design); only the printed name is pre-filled.
- Est. 2 h on top of Phases A–D. Confirm with counsel that pre-printing the circulator's name on the affidavit form is acceptable; if they prefer it blank, it is a one-flag change (`prefill_affidavit_name: false`).
