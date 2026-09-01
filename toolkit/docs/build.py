"""Render every document from config/petition.yaml + reference/statutes + templates/docs.

    python -m toolkit.docs.build --out output/docs            # draft: placeholders allowed, watermarked
    python -m toolkit.docs.build --out output/final --final   # refuses while any placeholder remains
    ... --duplex short-edge                                   # rotate affidavit pages 180° for short-edge duplex
"""
from __future__ import annotations
import argparse, sys
from datetime import date
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markdown import markdown
from weasyprint import HTML
from toolkit import ROOT, statutes
from toolkit import config as cfg
from .roles import ROLES, ROLE_BY_KEY
from .helpers import (EXCLUSION_SHORT, WATERMARK_TEXT, source_doc_html, source_notes, strip_tags, watermark_data_uri)

TEMPLATES = ROOT / "templates" / "docs"
DOCS = {
    "01-petition-pamphlet": ("pamphlet.html", "Petition Pamphlet"),
    "02-ballot-title": ("ballot-title.html", "Proposed Ballot Title"),
    "03-circulator-quick-card": ("quick-card.html", "Circulator Quick Card"),
    "04-notary-checklist": ("notary-checklist.html", "Notary Checklist"),
    "05-action-plan": ("action-plan.html", "Referendum Action Plan"),
    "06-fallback-plan": ("fallback-plan.html", "Fallback Plan"),
    "07-training-cards": ("training-cards.html", "Volunteer Training Cards"),
}
DUPLEX_MODES = ("long-edge", "short-edge")


class PlaceholderError(RuntimeError):
    def __init__(self, items: list[str]):
        super().__init__("Final build refused — placeholders remain:\n  - " + "\n  - ".join(items))
        self.items = items


def env() -> Environment:
    e = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=select_autoescape(["html"]), trim_blocks=True, lstrip_blocks=True)
    e.filters["md"] = lambda s: markdown(s or "", extensions=["tables"])
    return e


def base_context(p: cfg.Petition, final: bool, duplex: str) -> dict:
    county = p.county
    L = p.layout
    return {
        "p": p, "f": p.fmt, "L": L, "final": final, "draft": not final, "duplex": duplex,
        "today": date.today().strftime("%B %-d, %Y"),
        "warning": statutes.warning_sentence(),
        "notice": statutes.open_records_notice(),
        "attestation": statutes.signer_attestation(county),
        "affidavit": statutes.affidavit(county),
        "five": statutes.FIVE_DATA_POINTS,
        "exclusions": statutes.exclusions(),
        "exclusions_short": EXCLUSION_SHORT,
        "source_notes": source_notes(p),
        "measure_html": markdown(p.measure.exact_text, extensions=["tables"]),
        "sheets": list(range(1, L.sheets_per_pamphlet + 1)),
        "rows": L.rows_per_sheet,
        "wm_portrait": watermark_data_uri(8.5, 14) if not final else "",
        "wm_landscape": watermark_data_uri(14, 8.5) if not final else "",
        "watermark_text": WATERMARK_TEXT,
        "eb": p.contacts.get("election_board", {}),
        "captain": p.contacts.get("petition_captain") or {},
        "cards": ROLES, "volunteer": None, "stamp": None,
    }


def render_pamphlet(petition: cfg.Petition, stamp: dict | None = None, duplex: str | None = None) -> bytes:
    """The pamphlet alone, optionally stamped per copy: {"number": "P-017", "issued_to": "Alex
    Rivera", "training_id": "V-0007"}. Stamps fill blanks only (pamphlet number, cover
    assignment line, affidavit printed name); the petition content is unchanged, so the
    stamped print matches the filed instrument under check.content_fingerprint()."""
    duplex = duplex or (petition.layout.duplex if petition.layout.duplex in DUPLEX_MODES else "long-edge")
    ctx = base_context(petition, final=True, duplex=duplex)
    ctx["stamp"] = stamp
    html = env().get_template(DOCS["01-petition-pamphlet"][0]).render(doc_key="01-petition-pamphlet", doc_title="Petition Pamphlet", **ctx)
    return HTML(string=html, base_url=str(TEMPLATES)).write_pdf()


def render_training_card(role_key: str, volunteer: dict | None = None, petition: cfg.Petition | None = None) -> bytes:
    """One role's training card (front + acknowledgment), optionally pre-filled for a volunteer
    ({"id", "name", "phone"}). Used by the admin's per-volunteer button."""
    p = petition or cfg.load()
    ctx = base_context(p, final=True, duplex="long-edge")           # no draft watermark on training material
    ctx["cards"] = [ROLE_BY_KEY[role_key]]
    ctx["volunteer"] = volunteer
    html = env().get_template(DOCS["07-training-cards"][0]).render(doc_key="07-training-cards", doc_title="Volunteer Training Card", **ctx)
    return HTML(string=html, base_url=str(TEMPLATES)).write_pdf()


def render_html(key: str, ctx: dict) -> str:
    template, title = DOCS[key]
    return env().get_template(template).render(doc_key=key, doc_title=title, **ctx)


def build_all(out: str | Path, final: bool = False, duplex: str = "long-edge", petition: cfg.Petition | None = None,
              only: list[str] | None = None) -> list[Path]:
    if duplex not in DUPLEX_MODES:
        raise ValueError(f"duplex must be one of {DUPLEX_MODES}")
    p = petition or cfg.load()
    if final and p.placeholders:
        raise PlaceholderError(p.placeholders)
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    ctx = base_context(p, final, duplex)
    ctx["action_plan_html"] = source_doc_html("action-plan", p)
    ctx["fallback_plan_html"] = source_doc_html("fallback-plan", p)
    written = []
    for key in (only or DOCS):
        html = render_html(key, ctx)
        if final:
            hits = sorted(set(m.group(0) for m in cfg.PLACEHOLDER_RE.finditer(strip_tags(html))))
            if hits:
                raise PlaceholderError([f"{key}: {h}" for h in hits])
        path = out / f"{key}.pdf"
        HTML(string=html, base_url=str(TEMPLATES)).write_pdf(str(path))
        written.append(path)
    return written


DOC_TITLES = {
    "01-petition-pamphlet.pdf": "Petition pamphlet — cover, petition, measure, signature sheets with affidavits (legal, duplex)",
    "02-ballot-title.pdf": "Proposed ballot title — separate filing (62 O.S. § 868(D))",
    "03-circulator-quick-card.pdf": "Circulator quick card (legal, duplex)",
    "04-notary-checklist.pdf": "Notary checklist + session log",
    "05-action-plan.pdf": "Action plan after adoption",
    "06-fallback-plan.pdf": "Fallback plan if the Board votes no",
    "07-training-cards.pdf": "Volunteer training cards — one per role, with signed training acknowledgment and wallet card",
}


def write_manifest(out_dir, paths, *, final: bool, duplex: str, petition) -> str:
    """Describe the build for the admin Documents page (and for print orders)."""
    import json, hashlib, subprocess
    from datetime import datetime, timezone
    from pathlib import Path
    from pypdf import PdfReader
    files = []
    for path in paths:
        path = Path(path)
        try:
            pages = len(PdfReader(str(path)).pages)
        except Exception:
            pages = None
        files.append({"name": path.name, "title": DOC_TITLES.get(path.name, path.stem), "bytes": path.stat().st_size,
                      "pages": pages, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5).stdout.strip() or None
    except Exception:
        sha = None
    manifest = {
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "final": final, "duplex": duplex,
        "git_sha": sha or __import__("os").environ.get("GIT_SHA"), "placeholders": petition.placeholders,
        "config": {"county": petition.county, "adoption_date": petition.fmt.adoption_date, "filing_deadline": petition.fmt.filing_deadline,
                   "election_date": petition.fmt.election_date, "registered_voters": petition.fmt.registered_voters,
                   "legal_minimum": petition.fmt.legal_minimum, "target": petition.fmt.target_signatures,
                   "rows_per_sheet": petition.layout.rows_per_sheet, "sheets_per_pamphlet": petition.layout.sheets_per_pamphlet},
        "files": files,
    }
    mp = Path(out_dir) / "manifest.json"
    mp.write_text(json.dumps(manifest, indent=2))
    return str(mp)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="output/docs")
    ap.add_argument("--final", action="store_true", help="filing build: refuse while placeholders remain; no watermark")
    ap.add_argument("--duplex", choices=DUPLEX_MODES, default=None, help="default: config layout.duplex")
    ap.add_argument("--only", nargs="*", choices=list(DOCS), help="render a subset")
    ap.add_argument("--from-db", nargs="?", const="", metavar="URL",
                    help="render from the DATABASE (admin-entered data) instead of the YAML seed; URL defaults to $DATABASE_URL")
    a = ap.parse_args(argv)
    if a.from_db is not None:
        import os
        if a.from_db:
            os.environ["DATABASE_URL"] = a.from_db
        from app.db import make_engine, database_url, init_db
        from sqlalchemy.orm import sessionmaker
        from app.petition import from_db
        eng = make_engine(database_url()); init_db(eng)
        with sessionmaker(bind=eng)() as session:
            p = from_db(session)
    else:
        p = cfg.load()
    duplex = a.duplex or (p.layout.duplex if p.layout.duplex in DUPLEX_MODES else "long-edge")
    try:
        paths = build_all(a.out, final=a.final, duplex=duplex, petition=p, only=a.only)
    except PlaceholderError as e:
        print(e, file=sys.stderr); return 2
    for path in paths:
        print(f"wrote {path}")
    write_manifest(a.out, paths, final=a.final, duplex=duplex, petition=p)
    if not a.final:
        print(f"draft build ({len(p.placeholders)} placeholders outstanding): " + "; ".join(p.placeholders))
    return 0


if __name__ == "__main__":
    sys.exit(main())
