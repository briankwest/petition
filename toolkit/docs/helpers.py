"""Template helpers: draft watermark, source-doc conversion, generated Source Notes."""
from __future__ import annotations
import base64, io, re
from functools import lru_cache
from markdown import markdown
from toolkit import ROOT, statutes
from toolkit.config import Petition

SOURCE_DIR = ROOT / "reference" / "source-docs"
SOURCE_DOCS = {
    "action-plan": "Action Plan After the 22nd.md",
    "fallback-plan": "Fallback Plan_ If Commissioners Vote NO.md",
    "quick-card": "Circulator Quick Card.md",
    "notary-checklist": "Notary Checklilst.md",
    "referendum": "Referendum Version 2, based on proposal.md",
}
WATERMARK_TEXT = "DRAFT — NOT FILED — DO NOT CIRCULATE"

# Short labels for the 34 O.S. § 6.1(A) exclusions (full text: statutes.exclusions()).
EXCLUSION_SHORT = [
    ("E1", "Sheet not verified by the circulator's affidavit", True),
    ("E2", "Signer is not a resident", False),
    ("E3", "Sheet detached from the petition pamphlet", True),
    ("E4", "More than one signature on a printed line", False),
    ("E5", "Signature not on a printed line", False),
    ("E6", "Signed a name other than their own, or signed more than once", False),
    ("E7", "Notary defect: no notary signature, no seal, expired commission, or no expiration date", True),
    ("E8", "Cannot be matched to the State Election Board's voter registration records", False),
]  # third field: True = the WHOLE SHEET is excluded

STATUTE_SUMMARY = {
    "62-868": "Local Development Act initiative and referendum: form per 34 O.S. §§ 1–2; true copy filed with the "
              "Secretary of the County Election Board before circulation; 10% of registered county voters; signed "
              "copies within 30 days after adoption; county count, publication and 10-day protest; ballot title ≤ 150 "
              "words reviewed by the District Attorney within 3 days; vote at the next general county election.",
    "34-1": "Referendum petition form; the five signer data points (legal first name, legal last name, ZIP code, house "
            "number, birth month/day); four of five must match the voter file; 30 days for county measures.",
    "34-3": "Pamphlet = copy of the petition + attached signature sheets; the word 'Warning' and the felony sentence in "
            "at least ten-point type on the outer page; the gist on the top margin of every signature sheet; Open "
            "Records Act notice under the gist.",
    "34-6": "Circulator must be a registered Oklahoma voter and verify each sheet by affidavit on its back; notary "
            "signature, title, address, commission number, expiration date and seal.",
    "34-6.1": "The eight grounds on which signatures are not counted (defect codes E1–E8).",
    "34-23": "Who may sign; signing another's name, signing twice, or signing when not a legal voter is a felony.",
    "34-24": "Substantial compliance; clerical errors disregarded (do not rely on it).",
}


@lru_cache(maxsize=4)
def watermark_data_uri(width_in: float, height_in: float, text: str = WATERMARK_TEXT) -> str:
    """Raster watermark (matplotlib) so it is not extractable text and never trips the text checks."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig = plt.figure(figsize=(width_in, height_in), dpi=50)
    fig.patch.set_alpha(0)
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_axis_off()
    size = 30 if width_in < height_in else 40
    ax.text(0.5, 0.5, text, rotation=45 if width_in < height_in else 25, ha="center", va="center",
            fontsize=size, fontweight="bold", color=(0.72, 0.1, 0.1, 0.16), transform=ax.transAxes)
    buf = io.BytesIO(); fig.savefig(buf, format="png", transparent=True, dpi=50); plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def source_notes(p: Petition) -> list[dict]:
    out = []
    for sec in p.statutes:
        h = statutes.header(sec)
        out.append({"cite": h["cite"], "title": h.get("title", "").split("—", 1)[-1].strip(),
                    "url": statutes.cite_url(sec), "retrieved": h.get("retrieved", "").split(" ")[0],
                    "summary": STATUTE_SUMMARY.get(sec, "")})
    return out


def source_notes_html(p: Petition) -> str:
    items = "".join(f'<p class="note"><strong>{n["cite"]} — {n["title"]}.</strong> {n["summary"]} '
                    f'<span class="url">{n["url"]}</span> (retrieved {n["retrieved"]})</p>' for n in source_notes(p))
    return f'<div class="source-notes">{items}</div>'


def read_source(key: str) -> str:
    return (SOURCE_DIR / SOURCE_DOCS[key]).read_text(encoding="utf-8")


def _replace_dates(md: str, p: Petition) -> str:
    f = p.fmt
    subs = [
        (r"AFTER THE JUNE 22 VOTE", "AFTER THE COMMISSION VOTE"),
        (r"June 23-24, 2026", "Within 1–2 days after adoption"),
        (r"July 22, 2026", f.filing_deadline),
        (r"June 22, 2026", f.adoption_date),
        (r"Before June 22", "Before the vote"),
        (r"June 22", f.adoption_date),
    ]
    for pat, rep in subs:
        md = re.sub(pat, lambda _m, r=rep: r, md)
    return md


def source_doc_html(key: str, p: Petition) -> str:
    """Google-Docs markdown export -> HTML with config-derived dates, numbers and Source Notes."""
    md = read_source(key)
    md = _replace_dates(md, p)
    md = md.replace("\\[ \\]", "☐ ")
    if key == "action-plan":
        md = re.sub(r"(☐ Calculate 10% of that number[^\n]*)",
                    lambda m: m.group(1) + f"\n\n☐ Current figures — registered voters on file: {p.fmt.registered_voters}; "
                    f"legal minimum (10%): {p.fmt.legal_minimum}; working target (15%): {p.fmt.target_signatures}\\.", md)
        md = re.sub(r"(# \*\*Source Notes\*\*\n)(.*?)(?=# \*\*Legal Caution\*\*)", r"\1\nSOURCE_NOTES_TOKEN\n\n", md, flags=re.S)
    elif key == "fallback-plan":
        md = re.sub(r"(\*\*16\\\. Source Notes for Petition Context\*\*\n)(.*?)(?=\*\*17\\\.)",
                    r"\1\nThese notes keep the campaign team oriented. Update them if election officials, counsel, or the final filing uses a different route.\n\nSOURCE_NOTES_TOKEN\n\n", md, flags=re.S)
    html = markdown(md, extensions=["tables"])
    html = html.replace("<p>SOURCE_NOTES_TOKEN</p>", source_notes_html(p))
    return html


def strip_tags(html: str) -> str:
    import html as _h
    return _h.unescape(re.sub(r"<[^>]+>", " ", html))
