"""Statutory + layout checks on the rendered PDFs (PLAN.md §6).

    python -m toolkit.docs.check output/docs            # draft checks
    python -m toolkit.docs.check output/final --final   # + no placeholders, no DRAFT, matches the filed hash
Exit status 1 on any failure.
"""
from __future__ import annotations
import argparse, hashlib, re, sys
from dataclasses import dataclass, field
from pathlib import Path
import pdfplumber
from toolkit import ROOT, statutes
from toolkit import config as cfg
from .build import DOCS

LEGAL_SIZES = {(612, 1008), (1008, 612)}
MIN_PT = 10.0 - 0.05
FILED_DIR = ROOT / "output" / "filed"


@dataclass
class Result:
    doc: str
    check: str
    ok: bool
    detail: str = ""


@dataclass
class Page:
    idx: int
    width: float
    height: float
    text: str            # whitespace-normalised
    rtext: str           # reversed (for pages rotated 180° in short-edge duplex mode)
    lower: str
    rlower: str
    chars: list = field(repr=False, default_factory=list)
    words: list = field(repr=False, default_factory=list)
    variants: list = field(repr=False, default_factory=list)   # full page + column crops, each normal and reversed

    def has(self, phrase: str, ci: bool = False) -> bool:
        ph = norm(phrase)
        if ci:
            ph = ph.lower(); return any(ph in v.lower() for v in self.variants)
        return any(ph in v for v in self.variants)

    def find(self, pattern: str):
        for v in self.variants:
            if (m := re.search(pattern, v)):
                return m
        return None


def norm(s: str | None) -> str:
    return " ".join((s or "").split())


def load(pdf: Path) -> list[Page]:
    pages = []
    with pdfplumber.open(str(pdf)) as d:
        for i, pg in enumerate(d.pages, 1):
            raw = pg.extract_text() or ""
            t, rt = norm(raw), norm(raw[::-1])
            # Two-column pages (affidavit + notary block) interleave lines in whole-page extraction,
            # so also read overlapping left/right crops; reversed copies cover 180°-rotated pages.
            w, h = float(pg.width), float(pg.height)
            crops = [pg.crop(box).extract_text() or "" for f in (0.5, 0.55, 0.6, 0.66)
                     for box in ((0, 0, w * f, h), (w * (1 - f), 0, w, h))]
            variants = [t, rt] + [norm(c) for c in crops] + [norm(c[::-1]) for c in crops]
            pages.append(Page(i, w, h, t, rt, t.lower(), rt.lower(), chars=pg.chars, words=pg.extract_words(), variants=variants))
    return pages


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fingerprint(pages: list[Page]) -> str:
    """Content fingerprint: page sizes + text. Stable across rebuilds even if PDF metadata differs."""
    h = hashlib.sha256()
    for p in pages:
        h.update(f"{int(p.width)}x{int(p.height)}|{p.text}\n".encode())
    return h.hexdigest()


def content_fingerprint(pages: list["Page"], ignore: tuple[str, ...] | list[str] = ()) -> str:
    """Fingerprint for filed-vs-print comparison. Unlike fingerprint(), it strips underscore
    blanks and any per-pamphlet stamp strings (pamphlet number, assignee name, training ID)
    so a stamped print compares equal to the unstamped filed instrument when the petition
    content is identical — and differs whenever the petition content itself changed."""
    h = hashlib.sha256()
    ig = [norm(s) for s in ignore if s]
    for p in pages:
        t = p.text
        for s in ig:
            t = t.replace(s, " ")
        t = re.sub(r"_+", " ", t)
        t = re.sub(r"\( *\)", " ", t)              # empty parens left by a removed stamp line
        # order-insensitive: filling a blank can reflow pdfplumber's two-column extraction order,
        # so hash the sorted bag of words — any added/removed/changed word still changes the hash
        words = " ".join(sorted(re.sub(r"\s+", " ", t).split()))
        h.update(f"{int(p.width)}x{int(p.height)}|{words}\n".encode())
    return h.hexdigest()


def read_filed() -> dict:
    out = {}
    for name in ("SHA256SUMS", "FINGERPRINT"):
        f = FILED_DIR / name
        if f.exists():
            for line in f.read_text().splitlines():
                parts = line.split()
                if len(parts) == 2:
                    out.setdefault(parts[1], {})[name] = parts[0]
    return out


def run_checks(out_dir: str | Path, final: bool = False, petition: cfg.Petition | None = None,
               only: list[str] | None = None) -> list[Result]:
    p = petition or cfg.load()
    out_dir = Path(out_dir)
    R: list[Result] = []
    keys = only or list(DOCS)
    docs: dict[str, list[Page]] = {}
    for key in keys:
        f = out_dir / f"{key}.pdf"
        if not f.exists():
            R.append(Result(key, "exists", False, f"missing {f}")); continue
        docs[key] = load(f)
        R.append(Result(key, "exists", True, f"{len(docs[key])} pages"))

    # ---- every document ----
    for key, pages in docs.items():
        bad = [(pg.idx, int(pg.width), int(pg.height)) for pg in pages if (int(pg.width), int(pg.height)) not in LEGAL_SIZES]
        R.append(Result(key, "legal page size (8.5×14 in)", not bad, f"{len(pages)} pages" if not bad else f"non-legal pages: {bad}"))
        small = [(pg.idx, round(c["size"], 2), c["text"]) for pg in pages for c in pg.chars if c["text"].strip() and c["size"] < MIN_PT]
        R.append(Result(key, "no type below 10 pt (34 O.S. § 3)", not small, "" if not small else f"{len(small)} glyphs, e.g. {small[:3]}"))
        if final:
            hits = sorted({m.group(0) for pg in pages for m in cfg.PLACEHOLDER_RE.finditer(pg.text)} |
                          {m.group(0) for pg in pages for m in cfg.PLACEHOLDER_RE.finditer(pg.rtext)})
            R.append(Result(key, "final: no placeholders", not hits, "; ".join(hits)[:200]))
            drafty = [pg.idx for pg in pages if re.search(r"\bDRAFT\b", pg.text) or re.search(r"\bDRAFT\b", pg.rtext)]
            R.append(Result(key, "final: no DRAFT marking", not drafty, f"pages {drafty}" if drafty else ""))

    # ---- pamphlet ----
    key = "01-petition-pamphlet"
    if key in docs:
        pages = docs[key]
        L = p.layout
        cover = pages[0]
        R.append(Result(key, "cover: the word 'Warning' (34 O.S. § 3(A))", "warning" in cover.lower, ""))
        R.append(Result(key, "cover: felony sentence verbatim (34 O.S. § 3(A))", cover.has(statutes.warning_sentence()), ""))
        wchars = [c for c in cover.chars if c["text"].strip()]
        R.append(Result(key, f"cover: warning type ≥ {L.warning_pt} pt", bool(wchars) and max(c["size"] for c in wchars) >= L.warning_pt, ""))
        pet = next((pg for pg in pages if pg.has("Petition for Referendum")), None)
        R.append(Result(key, "petition page present", pet is not None, ""))
        if pet:
            for label, phrase in [
                ("signer attestation (34 O.S. § 1)", statutes.signer_attestation(p.county)),
                ("five data points (34 O.S. § 1)", "legal first name, legal last name, zip code, house number and numerical month and day of my birth"),
                ("30-day filing statement (62 O.S. § 868(B)(3))", "not more than thirty (30) days after the passage or adoption of the resolution"),
                ("filing deadline string", p.fmt.filing_deadline),
                ("the question (34 O.S. § 1)", "Shall the following resolution (local legislation) be approved?"),
                ("addressed to the chairman", f"To the Honorable {p.addressee.name}, {p.addressee.title}"),
            ]:
                R.append(Result(key, f"petition: {label}", pet.has(phrase), ""))
        sheets = [(pg, int(m.group(1)), int(m.group(2))) for pg in pages if (m := pg.find(r"SIGNATURE SHEET (\d+) OF (\d+)"))]
        affs = {pg.idx: int(m.group(1)) for pg in pages if (m := pg.find(r"verifies Signature Sheet (\d+) of this pamphlet"))}
        R.append(Result(key, f"{L.sheets_per_pamphlet} signature sheets", len(sheets) == L.sheets_per_pamphlet, f"found {len(sheets)}"))
        R.append(Result(key, "sheet pages are fronts (odd page numbers)", all(pg.idx % 2 == 1 for pg, _, _ in sheets), str([pg.idx for pg, _, _ in sheets])))
        R.append(Result(key, "sheet pages are landscape", all(pg.width > pg.height for pg, _, _ in sheets), ""))
        pairing = all(affs.get(pg.idx + 1) == n for pg, n, _ in sheets)
        R.append(Result(key, "each sheet followed by its own affidavit (34 O.S. § 6)", pairing, f"affidavits at {sorted(affs)}"))
        R.append(Result(key, "no stray affidavit pages", len(affs) == len(sheets), ""))
        gist_ok = all(pg.has(p.gist) for pg, _, _ in sheets)
        R.append(Result(key, "gist on every sheet, identical to config (34 O.S. § 3(A))", gist_ok, ""))
        notice = statutes.open_records_notice()
        notice_ok = all(pg.has(notice) and pg.text.find(norm(notice)) > pg.text.find(norm(p.gist)) for pg, _, _ in sheets)
        R.append(Result(key, "Open Records notice under the gist (34 O.S. § 3(B))", notice_ok, ""))
        margin_pt = L.margins_in * 72
        for pg, n, _ in sheets:
            expected = set(range((n - 1) * L.rows_per_sheet + 1, n * L.rows_per_sheet + 1))
            nums = {int(w["text"]) for w in pg.words if w["text"].isdigit() and w["x0"] >= margin_pt - 6 and w["x1"] <= margin_pt + 0.4 * 72 + 6}
            R.append(Result(key, f"sheet {n}: {L.rows_per_sheet} numbered lines {min(expected)}–{max(expected)}", nums == expected, f"found {sorted(nums)}" if nums != expected else ""))
        req = statutes.affidavit(p.county)["required_phrases"]
        for idx, n in sorted(affs.items()):
            pg = pages[idx - 1]
            missing = [ph for ph in req if not pg.has(ph, ci=True)]
            R.append(Result(key, f"affidavit {n}: statutory text + notary fields (34 O.S. § 6)", not missing, f"missing {missing}" if missing else ""))
        if final:
            filed = read_filed().get("01-petition-pamphlet.pdf")
            if filed:
                f = out_dir / f"{key}.pdf"
                if filed.get("SHA256SUMS") == sha256(f):
                    R.append(Result(key, "matches filed pamphlet (bytes)", True, ""))
                elif filed.get("FINGERPRINT") == fingerprint(pages):
                    R.append(Result(key, "matches filed pamphlet (content; PDF metadata differs)", True, ""))
                else:
                    R.append(Result(key, "matches filed pamphlet", False, "content differs from output/filed — do not print"))

    # ---- ballot title ----
    key = "02-ballot-title"
    if key in docs:
        pages = docs[key]
        R.append(Result(key, "≤ 150 words (62 O.S. § 868(D)(1))", p.ballot_title_word_count <= 150, f"{p.ballot_title_word_count} words"))
        R.append(Result(key, "says what YES and NO votes do", "YES vote" in p.ballot_title and "NO vote" in p.ballot_title, ""))
        R.append(Result(key, "ballot title text printed", any(pg.has(p.ballot_title) for pg in pages), ""))
        R.append(Result(key, "word count printed", any(pg.has("Word count:") for pg in pages), ""))
        R.append(Result(key, "single page", len(pages) == 1, f"{len(pages)} pages"))

    # ---- cross-document consistency ----
    dl = p.fmt.filing_deadline
    for key in ("03-circulator-quick-card", "05-action-plan"):
        if key in docs:
            R.append(Result(key, "filing deadline identical to the pamphlet", any(pg.has(dl) for pg in docs[key]), dl))
    if "03-circulator-quick-card" in docs:
        R.append(Result("03-circulator-quick-card", "two pages (one duplex sheet)", len(docs["03-circulator-quick-card"]) == 2,
                        f"{len(docs['03-circulator-quick-card'])} pages"))
    if "04-notary-checklist" in docs:
        pgs = docs["04-notary-checklist"]
        ok = len(pgs) >= 2 and pgs[0].width < pgs[0].height and all(pg.width > pg.height for pg in pgs[1:])
        R.append(Result("04-notary-checklist", "portrait checklist + landscape session-log pages", ok,
                        f"{len(pgs)} pages: " + ", ".join("landscape" if pg.width > pg.height else "portrait" for pg in pgs)))
    for key in ("03-circulator-quick-card", "04-notary-checklist", "05-action-plan", "06-fallback-plan"):
        if key in docs:
            stale = [m for m in ("June 22", "July 22") if any(m in pg.text for pg in docs[key])]
            R.append(Result(key, "no hard-coded vote dates", not stale, ", ".join(stale)))
    if "04-notary-checklist" in docs:
        R.append(Result("04-notary-checklist", "defect codes E1–E8 (34 O.S. § 6.1)", all(any(pg.has(f"E{i} —") for pg in docs["04-notary-checklist"]) for i in range(1, 9)), ""))
    return R


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out_dir")
    ap.add_argument("--final", action="store_true")
    ap.add_argument("--only", nargs="*", choices=list(DOCS))
    a = ap.parse_args(argv)
    results = run_checks(a.out_dir, final=a.final, only=a.only)
    width = max(len(r.check) for r in results)
    for r in results:
        print(f"[{'PASS' if r.ok else 'FAIL'}] {r.doc:26} {r.check:<{width}}  {r.detail}")
    fails = [r for r in results if not r.ok]
    print(f"\n{len(results) - len(fails)} passed, {len(fails)} failed" + (" — FINAL mode" if a.final else ""))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
