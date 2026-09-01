"""Document pipeline: build → statutory checks. Run: pytest tests/test_docs.py -q"""
import pdfplumber, pytest
from pathlib import Path
from toolkit import config as cfg
from toolkit.docs import build, check

N = cfg.load().layout.sheets_per_pamphlet


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("docs")
    build.build_all(out, final=False, duplex="long-edge")
    return out


def texts(pdf: Path) -> list[str]:
    with pdfplumber.open(str(pdf)) as d:
        return [pg.extract_text() or "" for pg in d.pages]


def test_all_checks_pass(built):
    failures = [f"{r.doc}: {r.check} ({r.detail})" for r in check.run_checks(built) if not r.ok]
    assert not failures, "\n".join(failures)


def test_final_build_refuses_while_placeholders_remain(tmp_path):
    with pytest.raises(build.PlaceholderError) as e:
        build.build_all(tmp_path, final=True)
    assert any("adoption_date" in i for i in e.value.items)


def test_no_stale_hard_coded_dates(built):
    for pdf in sorted(built.glob("*.pdf")):
        joined = "\n".join(texts(pdf))
        assert "June 22" not in joined and "July 22" not in joined, pdf.name


def test_pamphlet_structure(built):
    pages = texts(built / "01-petition-pamphlet.pdf")
    first_sheet = next(i for i, t in enumerate(pages, 1) if "SIGNATURE SHEET 1 OF" in t)
    assert first_sheet % 2 == 1, "first sheet must be a front (odd) page"
    assert len(pages) == (first_sheet - 1) + 2 * N
    with pdfplumber.open(str(built / "01-petition-pamphlet.pdf")) as d:
        assert all((int(p.width), int(p.height)) in {(612, 1008), (1008, 612)} for p in d.pages)


def test_short_edge_duplex_pamphlet_passes(tmp_path):
    build.build_all(tmp_path, final=False, duplex="short-edge", only=["01-petition-pamphlet"])
    failures = [f"{r.check} ({r.detail})" for r in check.run_checks(tmp_path, only=["01-petition-pamphlet"]) if not r.ok]
    assert not failures, "\n".join(failures)


def test_training_cards_doc(tmp_path):
    from toolkit.docs import build
    from toolkit.docs.roles import ROLES
    from pypdf import PdfReader
    paths = build.build_all(tmp_path, only=["07-training-cards"])
    r = PdfReader(str(paths[0]))
    assert len(r.pages) == 2 * len(ROLES)
    for pg in r.pages:
        assert (float(pg.mediabox.width), float(pg.mediabox.height)) == (612.0, 1008.0)
    text = r.pages[2].extract_text()
    assert "Circulator" in text and "34 O.S. § 6" in text


def test_stamped_pamphlet_matches_filed_fingerprint(tmp_path):
    from toolkit import config as cfg
    from toolkit.docs.build import render_pamphlet
    from toolkit.docs.check import load, fingerprint, content_fingerprint
    p = cfg.load()
    p.measure.resolution_number, p.measure.title = "2026-42", "A Resolution Approving the Plan"
    from datetime import date as _d
    p.measure.adoption_date, p.election.date = _d(2026, 10, 5), _d(2026, 11, 10)
    p.measure.exact_text_override = "BE IT RESOLVED that the Plan is approved."
    p.proponents = [{"name": "Brian West", "address": "714 E Osage Ave", "city": "McAlester", "zip": "74501"}]
    p.contacts["petition_captain"] = {"name": "Casey Captain", "phone": "918-555-0111"}
    stamp = {"number": "P-017", "issued_to": "Alex Rivera", "training_id": "V-0007"}
    a, b = tmp_path / "plain.pdf", tmp_path / "stamped.pdf"
    a.write_bytes(render_pamphlet(p)); b.write_bytes(render_pamphlet(p, stamp=stamp))
    pa, pb = load(a), load(b)
    assert fingerprint(pa) != fingerprint(pb)                                  # raw text differs (stamps)
    ig = [stamp["number"], stamp["issued_to"], stamp["training_id"], "Issued to:"]
    assert content_fingerprint(pa) == content_fingerprint(pb, ignore=ig)       # same filed instrument
    # a petition-content change is still caught
    p.gist = p.gist + " Changed."
    c = tmp_path / "changed.pdf"; c.write_bytes(render_pamphlet(p, stamp=stamp))
    assert content_fingerprint(pa) != content_fingerprint(load(c), ignore=ig)


def _letter_pdf(pages=2) -> bytes:
    import io
    from pypdf import PdfWriter
    w = PdfWriter()
    for _ in range(pages):
        w.add_blank_page(width=612, height=792)          # LETTER, not legal
    buf = io.BytesIO(); w.write(buf)
    return buf.getvalue()


def test_pamphlet_includes_attachments_normalized_to_legal(tmp_path):
    from pypdf import PdfReader
    pdf = build.build_all(tmp_path, only=["01-petition-pamphlet"], attachments=[("adopted-resolution.pdf", _letter_pdf(2))])[0]
    r = PdfReader(str(pdf))
    assert {(round(float(p.mediabox.width)), round(float(p.mediabox.height))) for p in r.pages} == {(612, 1008), (1008, 612)}
    tx = texts(pdf)
    ex = [i for i, t in enumerate(tx, 1) if "Exhibit — adopted-resolution.pdf" in t]
    prop = next(i for i, t in enumerate(tx, 1) if "Proponents of Record" in t)
    sheet1 = next(i for i, t in enumerate(tx, 1) if "SIGNATURE SHEET 1 OF" in t)
    assert len(ex) == 2 and ex == list(range(ex[0], ex[0] + 2)) and ex[0] >= 4   # contiguous, after the measure text
    assert prop == ex[-1] + 1                             # proponents immediately follow the exhibits
    assert sheet1 % 2 == 1                                # duplex parity: sheet on a front page
    # odd page count attachment: break-before:right pads so the sheet still lands on a front
    pdf2 = build.build_all(tmp_path / "b", only=["01-petition-pamphlet"], attachments=[("x.pdf", _letter_pdf(1))])[0]
    tx2 = texts(pdf2)
    s2 = next(i for i, t in enumerate(tx2, 1) if "SIGNATURE SHEET 1 OF" in t)
    assert s2 % 2 == 1


def test_stamped_pamphlet_with_attachments_matches_fingerprint(tmp_path):
    from toolkit.docs.check import load, content_fingerprint
    att = [("res.pdf", _letter_pdf(2))]
    p = cfg.load()
    plain = build.render_pamphlet(p, attachments=att)
    stamp = {"number": "P-017", "issued_to": "Alex Rivera", "training_id": "V-0007"}
    stamped = build.render_pamphlet(p, stamp=stamp, attachments=att)
    a = tmp_path / "a.pdf"; a.write_bytes(plain)
    b = tmp_path / "b.pdf"; b.write_bytes(stamped)
    ig = [stamp["number"], stamp["issued_to"], stamp["training_id"], "Issued to:"]
    assert content_fingerprint(load(a)) == content_fingerprint(load(b), ignore=ig)
    # different attachments -> different instrument
    c = tmp_path / "c.pdf"; c.write_bytes(build.render_pamphlet(p, attachments=[("res.pdf", _letter_pdf(3))]))
    assert content_fingerprint(load(a)) != content_fingerprint(load(c))
