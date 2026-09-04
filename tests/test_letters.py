"""The records-request letters: sixteen of them render, the DocuPost CSV is within the platform's limits,
and nothing that must be filled in is left blank. PDF rendering is exercised on one letter to keep the
suite quick; the HTML path covers the rest."""
import csv, re
from datetime import date
from pathlib import Path
from toolkit.letters import build, data

SENDER = dict(name="Jane Q. Public", email="jane@example.org", address="100 Main Street", city="McAlester", state="OK", zip="74501", phone="918-555-0100")


def test_sixteen_letters_with_addresses_and_slugs():
    L = data.letters()
    assert [x["n"] for x in L] == list(range(1, 17))
    assert set(data.MAIL) == set(range(1, 17)) == set(data.SLUGS)
    for x in L:
        assert x["re"] and x["to"] and len(x["to"]) == 2, x["n"]
        assert x.get("paras") or x["items"], x["n"]


def test_html_renders_without_placeholders(tmp_path):
    r = build.build(tmp_path, SENDER, date(2026, 9, 8), html_only=True)
    assert len(r["letters"]) == 16
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
    build.build(tmp_path, SENDER, date(2026, 9, 8), html_only=True)
    rows = list(csv.DictReader((tmp_path / "docupost.csv").open()))
    assert [r["letter"] for r in rows if r["role"] == "recipient"] == [str(n) for n in range(1, 17)]
    assert sum(1 for r in rows if r["role"] == "copy") == len(data.COPIES)
    for r in rows:
        for k in ("name", "company", "address", "address2", "city", "state", "zip"):
            assert len(r[k]) <= 40, (r["letter"], k, r[k])                              # DocuPost truncates at 40
        assert re.fullmatch(r"[A-Z]{2}", r["state"]) and re.fullmatch(r"\d{5}", r["zip"]) and r["file"].endswith(".pdf")
    assert list(rows[0].keys()) == build.CSV_FIELDS


def test_one_pdf_renders_letter_size(tmp_path):
    r = build.build(tmp_path, SENDER, date(2026, 9, 8), only=[11])                    # the shortest letter
    from weasyprint import HTML
    pdf = tmp_path / r["letters"][0]["file"]
    assert pdf.read_bytes().startswith(b"%PDF") and r["letters"][0]["pages"] >= 1
    doc = HTML(string=(tmp_path / pdf.name.replace(".pdf", ".html")).read_text(), base_url=str(build.TEMPLATES)).render()
    assert (round(doc.pages[0].width), round(doc.pages[0].height)) == (816, 1056)     # 8.5 x 11 inches at 96 px, as DocuPost requires
    assert len(doc.pages) == r["letters"][0]["pages"]


def test_every_letter_is_one_sheet_front_and_back(tmp_path):
    # DocuPost prints double-sided; the builder steps the type size down until each letter is two pages or fewer,
    # and the closing is tied to the last paragraph so the signature never sits alone on a page.
    r = build.build(tmp_path, SENDER, date(2026, 9, 8))
    assert all(m["pages"] <= build.MAX_PAGES for m in r["letters"]), [(m["file"], m["pages"]) for m in r["letters"] if m["pages"] > build.MAX_PAGES]
    assert all(m["font_pt"] >= build.SIZES[-1] for m in r["letters"])


def test_signature_png_is_embedded(tmp_path):
    from PIL import Image
    sig = tmp_path / "sig.png"
    Image.new("RGBA", (400, 120), (0, 0, 0, 0)).save(sig)
    uri = build.signature_uri(sig)
    assert uri.startswith("data:image/png;base64,")
    r = build.build(tmp_path / "out", SENDER, date(2026, 9, 8), only=[11], sig_uri=uri, html_only=True)
    html = (tmp_path / "out" / r["letters"][0]["file"].replace(".pdf", ".html")).read_text()
    assert 'class="sig" src="data:image/png;base64,' in html and 'class="sig-gap"' not in html
