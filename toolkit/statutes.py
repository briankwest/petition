"""Verbatim statute text from reference/statutes/*.txt, plus the exact fragments the
templates print and the checker verifies. Templates and checks MUST both go through
these helpers so a wording drift in one is caught by the other."""
from __future__ import annotations
import re
from functools import lru_cache
from . import ROOT

DIR = ROOT / "reference" / "statutes"
FIVE_DATA_POINTS = ["legal first name", "legal last name", "zip code", "house number", "numerical month and day of birth"]


@lru_cache
def _read(sec: str) -> tuple[dict, str]:
    txt = (DIR / f"{sec}.txt").read_text(encoding="utf-8")
    head, body = {}, []
    for line in txt.splitlines():
        if line.startswith("# ") and not body:
            if line.startswith("# Source:"): head["source"] = line[len("# Source:"):].strip()
            elif line.startswith("# HTML:"): head["html"] = line[len("# HTML:"):].strip()
            elif line.startswith("# Retrieved:"): head["retrieved"] = line[len("# Retrieved:"):].strip()
            else: head["title"] = line[2:].strip()
        else:
            body.append(line)
    return head, "\n".join(body).strip()


def header(sec: str) -> dict:
    h, _ = _read(sec); return {"cite": cite(sec), **h}

def text(sec: str) -> str:
    return _read(sec)[1]

def cite(sec: str) -> str:
    title, num = sec.split("-", 1)
    return f"{title} O.S. § {num}"

def cite_url(sec: str) -> str:
    src = header(sec).get("source", "")
    return src.split(" ")[0] if src else ""

def html_url(sec: str) -> str:
    """A human-readable web page for the section (OSCN for Title 34; Justia for § 868, whose
    official text is only published as a PDF)."""
    h = header(sec)
    if h.get("html"):
        return h["html"].split(" ")[0]
    src = cite_url(sec)
    return src if not src.lower().endswith(".pdf") else ""


def official_url(sec: str) -> str:
    """The official source we quoted from (may be a PDF)."""
    return cite_url(sec)


def available() -> list[str]:
    return sorted(p.stem for p in DIR.glob("*.txt"))


def warning_sentence() -> str:
    """The felony sentence 34 O.S. § 3(A) requires under the word 'Warning', verbatim."""
    m = re.search(r"“(It is a felony[^”]+)”", text("34-3"))
    return m.group(1).strip()


def open_records_notice() -> str:
    return "A copy of this petition and all signatures on this petition are public records subject to the Oklahoma Open Records Act."


def signer_attestation(county: str) -> str:
    """The 'each for himself says' clause from the 34 O.S. § 1 form, county variant."""
    return (f"and each for himself says: I have personally signed this petition; I am a legal voter of the "
            f"State of Oklahoma and of the county of {county}; the following five data points shall be included "
            f"on the form: the voter's legal first name, legal last name, zip code, house number and numerical "
            f"month and day of my birth.")


def affidavit(county: str) -> dict:
    """34 O.S. § 6 affidavit, verbatim, with the county venue and the county-of-signer clause filled in
    and the '(as the case may be)' city alternative removed. Blanks are kept as underscores."""
    body = (f"I, ____________________, being first duly sworn, say: That I am at least eighteen (18) years old, "
            f"a registered voter of this state, and that all signatures on the signature sheet were signed in my "
            f"presence; I believe that each has stated his or her name, mailing address, county of residence, and "
            f"date of birth associated with his or her Oklahoma voter registration record, and that each signer is a "
            f"legal voter of the State of Oklahoma and county of {county}.")
    return {
        "venue": f"State of Oklahoma, County of {county}, ss.",
        "body": body,
        "affiant_line": "(Signature and complete address of affiant.)",
        "jurat": "Subscribed and sworn to before me this ________ day of ________________ A.D. 20____.",
        "notary_line": ("(Signature and title of the Oklahoma notarial officer before whom oath is made, and his or her "
                        "complete address, commission number and expiration date, and official Oklahoma notary public seal.)"),
        # the phrases the checker looks for on every affidavit page
        "required_phrases": [
            "being first duly sworn", "at least eighteen (18) years old", "a registered voter of this state",
            "were signed in my presence", "mailing address, county of residence, and date of birth",
            f"legal voter of the State of Oklahoma and county of {county}", "Subscribed and sworn to before me",
            "commission number", "expiration date", "seal",
        ],
    }


def exclusions() -> list[str]:
    """The eight grounds in 34 O.S. § 6.1(A) on which signatures are not counted (E1–E8)."""
    body = text("34-6.1")
    items = re.findall(r"^\s*(\d)\.\s+(.*?)(?=^\s*\d\.\s|^B\.)", body, flags=re.S | re.M)
    out = [re.sub(r"[;.]?\s*(?:and)?\s*$", "", " ".join(t.split())) for _, t in items]
    assert len(out) == 8, f"expected 8 exclusions, parsed {len(out)}"
    return out


def statutory_numbers() -> dict:
    """Numbers that appear in text and must match config/petition.yaml (checked by tests)."""
    s868 = " ".join(text("62-868").split())
    return {
        "county_fraction": 0.10 if "ten percent (10%)" in s868 else None,
        "referendum_days": 30 if "within thirty (30) days" in s868 else None,
        "protest_days": 10 if "within ten (10) days after the publication" in s868 else None,
        "ballot_title_words": 150 if "one hundred fifty words" in s868 else None,
        "da_review_days": 3 if "Within three (3) days" in s868 else None,
        "warning_min_pt": 10 if "ten-point type" in text("34-3") else None,
    }
