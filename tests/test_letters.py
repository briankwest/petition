"""The records-request letters: sixteen of them render, the DocuPost CSV is within the platform's limits,
and nothing that must be filled in is left blank. PDF rendering is exercised on one letter to keep the
suite quick; the HTML path covers the rest."""
import csv, re
import pytest
from datetime import date
from pathlib import Path
from toolkit.letters import build, data, tokens as T

SENDER = dict(name="Jane Q. Public", email="jane@example.org", address="100 Main Street", city="McAlester", state="OK", zip="74501", phone="918-555-0100")
TOKENS = {n: T.mint() for n in data.SLUGS}                                                # never the real ones: those live in config/tokens.local.json


def test_sixteen_letters_with_addresses_and_slugs():
    L = data.letters()
    assert [x["n"] for x in L] == list(range(1, 18))
    assert set(data.MAIL) == set(range(1, 18)) == set(data.SLUGS)
    for x in L:
        assert x["re"] and x["to"] and len(x["to"]) == 2, x["n"]
        assert x.get("paras") or x["items"], x["n"]


def test_html_renders_without_placeholders(tmp_path):
    r = build.build(tmp_path, SENDER, date(2026, 9, 8), html_only=True, tokens=TOKENS)
    assert len(r["letters"]) == 17
    for m in r["letters"]:
        html = (tmp_path / m["file"].replace(".pdf", ".html")).read_text()
        assert "8 September 2026" in html and "Jane Q. Public" in html and "100 Main Street" in html
        assert "[date]" not in html and "[phone]" not in html and "{" not in html.split("<body>")[1], m["file"]   # no unfilled format fields
        assert 'class="sig-gap"' in html                                                 # no signature given: a gap, not a broken image
    federal = (tmp_path / "16-mcaap-army-foia.html").read_text()
    assert "5 U.S.C. § 552" in federal and "51 O.S." not in federal                     # the Army letter is FOIA, not the Oklahoma Act
    county = (tmp_path / "01-county-board-and-committee.html").read_text()
    assert "51 O.S. § 24A.1" in county and "27 January 2026" in county and "Floyd &amp; Driver" not in county and "Floyd & Driver" in county


def test_docupost_csv_within_limits(tmp_path):
    build.build(tmp_path, SENDER, date(2026, 9, 8), html_only=True, tokens=TOKENS)
    rows = list(csv.DictReader((tmp_path / "docupost.csv").open()))
    assert [r["letter"] for r in rows if r["role"] == "recipient"] == [str(n) for n in range(1, 18)]
    assert sum(1 for r in rows if r["role"] == "copy") == len(data.COPIES)
    for r in rows:
        for k in ("name", "company", "address", "address2", "city", "state", "zip"):
            assert len(r[k]) <= 40, (r["letter"], k, r[k])                              # DocuPost truncates at 40
        assert re.fullmatch(r"[A-Z]{2}", r["state"]) and re.fullmatch(r"\d{5}", r["zip"]) and r["file"].endswith(".pdf")
    assert list(rows[0].keys()) == build.CSV_FIELDS


def test_one_pdf_renders_letter_size(tmp_path):
    r = build.build(tmp_path, SENDER, date(2026, 9, 8), only=[11], tokens=TOKENS)                    # the shortest letter
    from weasyprint import HTML
    pdf = tmp_path / r["letters"][0]["file"]
    assert pdf.read_bytes().startswith(b"%PDF") and r["letters"][0]["pages"] >= 1
    doc = HTML(string=(tmp_path / pdf.name.replace(".pdf", ".html")).read_text(), base_url=str(build.TEMPLATES)).render()
    assert (round(doc.pages[0].width), round(doc.pages[0].height)) == (816, 1056)     # 8.5 x 11 inches at 96 px, as DocuPost requires
    assert len(doc.pages) == r["letters"][0]["pages"]


def test_every_letter_is_one_sheet_front_and_back(tmp_path):
    # DocuPost prints double-sided; the builder steps the type size down until each letter is two pages or fewer,
    # and the closing is tied to the last paragraph so the signature never sits alone on a page.
    r = build.build(tmp_path, SENDER, date(2026, 9, 8), tokens=TOKENS)
    assert all(m["pages"] <= build.MAX_PAGES for m in r["letters"]), [(m["file"], m["pages"]) for m in r["letters"] if m["pages"] > build.MAX_PAGES]
    assert all(m["font_pt"] >= build.SIZES[-1] and m["leading"] in build.LEADINGS for m in r["letters"])
    assert all(m["font_pt"] >= 9 for m in r["letters"]), [(m["file"], m["font_pt"]) for m in r["letters"] if m["font_pt"] < 9]   # the county letter is the long one; nothing goes to 8.5


def test_signature_png_is_embedded(tmp_path):
    from PIL import Image
    sig = tmp_path / "sig.png"
    Image.new("RGBA", (400, 120), (0, 0, 0, 0)).save(sig)
    uri = build.signature_uri(sig)
    assert uri.startswith("data:image/png;base64,")
    r = build.build(tmp_path / "out", SENDER, date(2026, 9, 8), only=[11], sig_uri=uri, html_only=True, tokens=TOKENS)
    html = (tmp_path / "out" / r["letters"][0]["file"].replace(".pdf", ".html")).read_text()
    assert 'class="sig" src="data:image/png;base64,' in html and 'class="sig-gap"' not in html


def test_tokens_mint_hash_and_lookup(tmp_path):
    local, public = tmp_path / "tokens.local.json", tmp_path / "tokens.json"
    minted = T.issue(local=local, public=public, today=date(2026, 9, 5))
    assert minted == sorted(data.SLUGS)
    mine, pub = T.load_local(local), T.load_public(public)
    toks = [e["token"] for e in mine.values()]
    assert len(set(toks)) == 17 and all(len(x) == 32 and set(x) <= set(T.ALPHABET) for x in toks)
    for n, e in mine.items():
        assert pub["letters"][str(n)]["sha256"] == T.digest(e["token"]) and pub["letters"][str(n)]["slug"] == data.SLUGS[n]
        assert e["token"] not in public.read_text()                                          # the committed file never holds a plain token
    tok = mine[3]["token"]
    assert T.lookup(tok, public)["n"] == 3 and T.lookup(T.display(tok).lower(), public)["n"] == 3   # typed with hyphens, any case
    assert T.lookup(tok[:-1] + ("A" if tok[-1] != "A" else "B"), public) is None and T.lookup("short", public) is None
    assert T.issue(local=local, public=public) == []                                         # idempotent
    assert T.issue(reissue=[3], local=local, public=public, today=date(2026, 9, 6)) == [3]
    assert T.lookup(tok, public) is None and len(T.load_public(public)["letters"]["3"]["retired"]) == 1   # the old one is retired, on the record
    assert T.url(tok) == T.PORTAL + tok and T.url(tok, pretty=True).count("-") == 7


def test_mailed_letters_carry_the_token_and_public_copies_do_not(tmp_path):
    build.build(tmp_path / "mail", SENDER, date(2026, 9, 8), html_only=True, tokens=TOKENS)
    build.build(tmp_path / "web", SENDER, date(2026, 9, 8), html_only=True, tokens=TOKENS, public=True)
    for n, slug in data.SLUGS.items():
        mail = (tmp_path / "mail" / f"{n:02d}-{slug}.html").read_text()
        web = (tmp_path / "web" / f"{n:02d}-{slug}.html").read_text()
        assert T.display(TOKENS[n]) in mail and 'class="qr"' in mail and "data:image/svg+xml" in mail and "Responding online" in mail, n
        assert TOKENS[n] not in web and T.display(TOKENS[n]) not in web and 'class="qr"' not in web, n
        assert "100 Main Street" not in web and "918-555-0100" not in web and "jane@example.org" in web, n   # public copies: name and email only
        for other, tok in TOKENS.items():
            if other != n:
                assert T.display(tok) not in mail, (n, other)                                # one token per letter
    assert not (tmp_path / "web" / "docupost.csv").exists() and (tmp_path / "mail" / "docupost.csv").exists()
    with pytest.raises(SystemExit):
        build.build(tmp_path / "bare", SENDER, date(2026, 9, 8), html_only=True, tokens={})  # a mailed letter without a token is refused
    build.build(tmp_path / "bare", SENDER, date(2026, 9, 8), html_only=True, tokens={}, portal=False, only=[11])   # unless asked for
