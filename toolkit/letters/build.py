"""Render the records-request letters to PDF and write the DocuPost mailing-list CSV.

    python -m toolkit.letters.build --out output/letters                  # all sixteen, dated today
    python -m toolkit.letters.build --only 1,2,3 --date 2026-09-08         # a wave, with a fixed date
    python -m toolkit.letters.build --signature ~/sig.png                  # override the signature in sender.local.yaml
    python -m toolkit.letters.build --html-only                            # skip WeasyPrint (tests, quick checks)
    python -m toolkit.letters.build --public --out output/letters-public    # copies for the website: no token, address or phone

Every mailed letter carries its response token (config/tokens.local.json, minted by toolkit.letters.tokens) as a
URL in the closing paragraph and as a QR code beside the signature; the build refuses a letter without one unless
--no-portal is given.

Sender details come from config/sender.local.yaml (git-ignored; see config/sender.example.yaml). Output is
NN-slug.pdf and NN-slug.html per letter, docupost.csv, and manifest.json. DocuPost wants 8.5x11 PDFs with a
3/4-inch clear perimeter and adds its own address cover sheet, so the letter keeps 0.85-inch margins and an
ordinary addressee block. Each letter must fit one sheet front and back: the builder tries 10pt, then the same
size with tighter leading, then steps the size down, and stops at the first fit. CSV fields are capped at 40
characters, state two letters, ZIP five digits.
"""
from __future__ import annotations
import argparse, base64, csv, json, re, sys
from datetime import date
from pathlib import Path
import yaml
from jinja2 import Environment, FileSystemLoader
from toolkit import ROOT
from . import data
from . import tokens as T
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


SIZES = (10, 9.5, 9, 8.5)      # tried in order until the letter fits front and back
LEADINGS = (1.34, 1.27)        # normal leading first, then tighter, before the next size down
STEPS = [(s, l) for s in SIZES for l in LEADINGS]
MAX_PAGES = 2


def portal_block(token: str | None) -> dict | None:
    """What the template needs to print the response link: the pretty URL, the host and grouped code under the QR,
    and the QR itself as an SVG data URI encoding the compact URL."""
    if not token:
        return None
    import segno
    qr = segno.make(T.url(token), error="m").svg_data_uri(scale=4, border=1, dark="#111111", light=None)
    return dict(pretty=T.url(token, pretty=True).replace("https://", ""), host=T.PORTAL.replace("https://", ""), code=T.display(token), qr=qr)


def render_html(x: dict, sender: dict, when: date, sig_uri: str = "", font_size: float = SIZES[0], leading: float = LEADINGS[0],
                token: str | None = None, public: bool = False) -> str:
    t = env().get_template("records-letter.html")
    clauses = dict(OPEN=data.OPEN, PERIOD=data.PERIOD, FORMAT=data.FORMAT, FEES=data.FEES, WITHHOLD=data.WITHHOLD, RESPONSE=data.RESPONSE)
    return t.render(l=x, sender=sender, date=long_date(when), signature=sig_uri, federal=bool(x.get("paras")), font_size=font_size, leading=leading,
                    portal=None if public else portal_block(token), public=public, **clauses)


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


def build(out: Path, sender: dict, when: date, only: list[int] | None = None, sig_uri: str = "", html_only: bool = False,
          tokens: dict[int, str] | None = None, public: bool = False, portal: bool = True) -> dict:
    """tokens: {letter number: plain token}. None loads config/tokens.local.json. A mailed letter without a token is
    refused unless portal=False; public copies never carry one."""
    out.mkdir(parents=True, exist_ok=True)
    selected = only or [x["n"] for x in letters()]
    if tokens is None:
        tokens = {n: e["token"] for n, e in T.load_local().items()}
    if portal and not public:
        missing = [n for n in selected if not tokens.get(n)]
        if missing:
            sys.exit(f"no response token for letter(s) {missing}: run  python -m toolkit.letters.tokens issue  (or pass --no-portal)")
    filenames, manifest = {}, []
    for x in letters():
        if x["n"] not in selected:
            continue
        stem = f"{x['n']:02d}-{SLUGS[x['n']]}"
        pdf = out / f"{stem}.pdf"
        token = tokens.get(x["n"]) if portal else None
        pages, (size, leading) = None, STEPS[0]
        html = render_html(x, sender, when, sig_uri, size, leading, token, public)
        if not html_only:
            from weasyprint import HTML
            for size, leading in STEPS:              # tighten, then shrink, until it is a single sheet front and back
                html = render_html(x, sender, when, sig_uri, size, leading, token, public)
                doc = HTML(string=html, base_url=str(TEMPLATES)).render()
                if len(doc.pages) <= MAX_PAGES:
                    break
            doc.write_pdf(str(pdf))
            pages = len(doc.pages)
            if pages > MAX_PAGES:
                print(f"warning: {pdf.name} is {pages} pages even at {size}pt", file=sys.stderr)
        (out / f"{stem}.html").write_text(html)
        filenames[x["n"]] = pdf.name
        manifest.append(dict(letter=x["n"], title=x["title"], file=pdf.name, pages=pages, font_pt=size, leading=leading, re=x["re"], date=long_date(when),
                             public=public, token_sha256=T.digest(token) if token else None, mail=MAIL[x["n"]], copies=[m for k, m in COPIES if k == x["n"]]))
    rows = csv_rows(selected, filenames)
    if not public:                                   # website copies are not mailed
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
    ap.add_argument("--public", action="store_true", help="website copies: no token or QR, no street address or phone")
    ap.add_argument("--no-portal", action="store_true", help="mailed letters without the response link (not recommended)")
    a = ap.parse_args(argv)
    sender = load_sender(Path(a.sender))
    sig = signature_uri(a.signature or sender.get("signature"))
    when = date.fromisoformat(a.date) if a.date else date.today()
    only = [int(n) for n in a.only.split(",")] if a.only else None
    r = build(Path(a.out), sender, when, only, sig, a.html_only, public=a.public, portal=not a.no_portal)
    for m in r["letters"]:
        print(f"{m['file']:42s} {str(m['pages'] or '-'):>3s} page(s) at {m['font_pt']:>4}pt{' tight' if m['leading'] != LEADINGS[0] else '      '}  {m['title']}")
    if a.public:
        print(f"{len(r['letters'])} public copies: no tokens, street address or phone")
    else:
        print(f"docupost.csv: {len(r['rows'])} rows ({sum(1 for x in r['rows'] if x['role']=='recipient')} recipients, {sum(1 for x in r['rows'] if x['role']=='copy')} copies)"
              + ("" if sig else "  · no signature yet: a gap is left above the typed name") + ("" if not a.no_portal else "  · NO response links"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
