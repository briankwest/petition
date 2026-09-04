"""Render the records-request letters to PDF and write the DocuPost mailing-list CSV.

    python -m toolkit.letters.build --out output/letters                  # all sixteen, dated today
    python -m toolkit.letters.build --only 1,2,3 --date 2026-09-08         # a wave, with a fixed date
    python -m toolkit.letters.build --signature ~/sig.png                  # override the signature in sender.local.yaml
    python -m toolkit.letters.build --html-only                            # skip WeasyPrint (tests, quick checks)

Sender details come from config/sender.local.yaml (git-ignored; see config/sender.example.yaml). Output is
NN-slug.pdf and NN-slug.html per letter, docupost.csv, and manifest.json. DocuPost wants 8.5x11 PDFs with a
3/4-inch clear perimeter and adds its own address cover sheet, so the letter keeps one-inch margins and an
ordinary addressee block. CSV fields are capped at 40 characters, state two letters, ZIP five digits.
"""
from __future__ import annotations
import argparse, base64, csv, json, re, sys
from datetime import date
from pathlib import Path
import yaml
from jinja2 import Environment, FileSystemLoader
from toolkit import ROOT
from . import data
from .data import COPIES, MAIL, SLUGS, letters

TEMPLATES = ROOT / "templates" / "docs"
CSV_FIELDS = ["name", "company", "address", "address2", "city", "state", "zip", "letter", "file", "role"]
MAX = 40


def load_sender(path: Path) -> dict:
    if not path.exists():
        sys.exit(f"{path} not found. Copy config/sender.example.yaml to {path.name} and fill it in (it is git-ignored).")
    s = yaml.safe_load(path.read_text()) or {}
    missing = [k for k in ("name", "email", "address", "city", "state", "zip", "phone") if not s.get(k)]
    if missing:
        sys.exit(f"{path}: missing {', '.join(missing)}")
    s["zip"] = str(s["zip"])
    return s


def signature_uri(path: str | Path | None) -> str:
    """PNG with an alpha channel as a data URI, or '' when there is no signature yet (a gap is left instead)."""
    if not path:
        return ""
    p = Path(path).expanduser()
    if not p.exists():
        sys.exit(f"signature not found: {p}")
    from PIL import Image
    with Image.open(p) as im:
        if im.mode != "RGBA":
            print(f"note: {p.name} is {im.mode}, not RGBA; a flattened signature prints with a box around it", file=sys.stderr)
    return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode()


def long_date(d: date) -> str:
    return f"{d.day} {d.strftime('%B %Y')}"


def env() -> Environment:
    return Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=False, trim_blocks=True, lstrip_blocks=True)


def render_html(x: dict, sender: dict, when: date, sig_uri: str = "") -> str:
    t = env().get_template("records-letter.html")
    clauses = dict(OPEN=data.OPEN, PERIOD=data.PERIOD, FORMAT=data.FORMAT, FEES=data.FEES, WITHHOLD=data.WITHHOLD, RESPONSE=data.RESPONSE)
    return t.render(l=x, sender=sender, date=long_date(when), signature=sig_uri, federal=bool(x.get("paras")), **clauses)


def _clip(v: str) -> str:
    v = (v or "").strip()
    return v if len(v) <= MAX else v[:MAX]


def csv_rows(selected: list[int], filenames: dict[int, str]) -> list[dict]:
    rows = []
    for n in selected:
        m = MAIL[n]
        rows.append({**{k: _clip(m[k]) for k in ("name", "company", "address", "address2", "city", "state", "zip")}, "letter": str(n), "file": filenames[n], "role": "recipient"})
    for n, m in COPIES:
        if n in selected:
            rows.append({**{k: _clip(m[k]) for k in ("name", "company", "address", "address2", "city", "state", "zip")}, "letter": str(n), "file": filenames[n], "role": "copy"})
    for r in rows:
        assert re.fullmatch(r"[A-Z]{2}", r["state"]) and re.fullmatch(r"\d{5}", r["zip"]), r
    return rows


def build(out: Path, sender: dict, when: date, only: list[int] | None = None, sig_uri: str = "", html_only: bool = False) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    selected = only or [x["n"] for x in letters()]
    filenames, manifest = {}, []
    for x in letters():
        if x["n"] not in selected:
            continue
        stem = f"{x['n']:02d}-{SLUGS[x['n']]}"
        html = render_html(x, sender, when, sig_uri)
        (out / f"{stem}.html").write_text(html)
        pdf = out / f"{stem}.pdf"
        pages = None
        if not html_only:
            from weasyprint import HTML
            doc = HTML(string=html, base_url=str(TEMPLATES)).render()
            doc.write_pdf(str(pdf))
            pages = len(doc.pages)
        filenames[x["n"]] = pdf.name
        manifest.append(dict(letter=x["n"], title=x["title"], file=pdf.name, pages=pages, re=x["re"], date=long_date(when),
                             mail=MAIL[x["n"]], copies=[m for k, m in COPIES if k == x["n"]]))
    rows = csv_rows(selected, filenames)
    with (out / "docupost.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS); w.writeheader(); w.writerows(rows)
    (out / "manifest.json").write_text(json.dumps(dict(date=long_date(when), sender={k: sender[k] for k in ("name", "address", "city", "state", "zip")},
                                                       letters=manifest, csv="docupost.csv"), indent=2))
    return dict(letters=manifest, rows=rows)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="output/letters")
    ap.add_argument("--sender", default=str(ROOT / "config" / "sender.local.yaml"))
    ap.add_argument("--signature", help="PNG with alpha; overrides the sender file")
    ap.add_argument("--date", help="YYYY-MM-DD; default today")
    ap.add_argument("--only", help="comma-separated letter numbers, e.g. 1,2,3")
    ap.add_argument("--html-only", action="store_true")
    a = ap.parse_args(argv)
    sender = load_sender(Path(a.sender))
    sig = signature_uri(a.signature or sender.get("signature"))
    when = date.fromisoformat(a.date) if a.date else date.today()
    only = [int(n) for n in a.only.split(",")] if a.only else None
    r = build(Path(a.out), sender, when, only, sig, a.html_only)
    for m in r["letters"]:
        print(f"{m['file']:42s} {str(m['pages'] or '-'):>3s} page(s)  {m['title']}")
    print(f"docupost.csv: {len(r['rows'])} rows ({sum(1 for x in r['rows'] if x['role']=='recipient')} recipients, {sum(1 for x in r['rows'] if x['role']=='copy')} copies)"
          + ("" if sig else "  · no signature yet: a gap is left above the typed name"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
