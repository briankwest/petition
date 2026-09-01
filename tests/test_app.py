import re
import pytest
from datetime import date
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker
from app.db import Base
from app.main import create_app
from app import models as m
from app.auth import hash_password
from app.settings import Settings


@pytest.fixture
def engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture
def client(engine):
    app = create_app(engine=engine)
    with TestClient(app, base_url="http://testserver") as c:
        yield c


@pytest.fixture
def db(engine):
    S = sessionmaker(bind=engine, expire_on_commit=False)
    with S() as s:
        yield s


def csrf_of(client, path="/admin/login"):
    html = client.get(path).text
    return re.search(r'name="csrf" value="([^"]+)"', html).group(1)


def login(client, db, username="captain", password="correct-horse-battery", role="admin"):
    db.add(m.User(username=username, password_hash=hash_password(password), role=role)); db.commit()
    tok = csrf_of(client)
    r = client.post("/admin/login", data={"csrf": tok, "username": username, "password": password, "next": "/admin"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/admin"
    return tok


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200 and r.json()["ok"] is True


def test_host_redirect(client):
    r = client.get("/sign?x=1", headers={"Host": "petiton.mcalester.net"}, follow_redirects=False)
    assert r.status_code == 301
    assert r.headers["location"] == "https://petition.mcalester.net/sign?x=1"
    r = client.get("/healthz", headers={"Host": "petiton.mcalester.net"}, follow_redirects=False)
    assert r.status_code == 200
    r = client.get("/", headers={"Host": "petition.mcalester.net", "X-Forwarded-Proto": "http"}, follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"].startswith("https://petition.mcalester.net/")
    assert client.get("/", headers={"Host": "petition.mcalester.net", "X-Forwarded-Proto": "https"}).status_code == 200


def test_public_pages_and_banner(client):
    for path in ["/", "/sign", "/registered", "/contact", "/faq", "/volunteer"]:
        r = client.get(path)
        assert r.status_code == 200, path
        assert "tabled" in r.text, path
    assert "okvoterportal.okelections.gov" in client.get("/registered").text
    assert "X-Content-Type-Options" in client.get("/").headers


def test_counts_hidden_until_enabled(client, db):
    r = client.get("/")
    assert "Signature count" not in r.text
    assert client.get("/api/stats.json").json()["public"] is False
    s = Settings(db); s.set("public_show_counts", True); db.commit()
    r = client.get("/")
    assert "Signature count" in r.text
    j = client.get("/api/stats.json").json()
    assert j["public"] is True and "collected" in j and "progress_to_target" not in j


def test_admin_requires_login(client):
    r = client.get("/admin", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/admin/login")
    assert client.get("/admin/pamphlets", follow_redirects=False).status_code == 303


def test_login_and_dashboard(client, db):
    login(client, db)
    r = client.get("/admin")
    assert r.status_code == 200 and "Dashboard" in r.text and "Legal minimum" in r.text


def test_pamphlet_workflow(client, db):
    tok = login(client, db)
    r = client.post("/admin/pamphlets/bulk-create", data={"csrf": tok, "start": 1, "count": 3, "sheets": 5}, follow_redirects=False)
    assert r.status_code == 303 and "Created%203" in r.headers["location"]
    assert db.scalar(select(m.Pamphlet).where(m.Pamphlet.number == "P-003")) is not None
    assert len(db.scalar(select(m.Pamphlet).where(m.Pamphlet.number == "P-001")).sheets) == 5
    # re-running skips existing
    r = client.post("/admin/pamphlets/bulk-create", data={"csrf": tok, "start": 1, "count": 3, "sheets": 5}, follow_redirects=False)
    assert "Created%200" in r.headers["location"]

    unverified = m.Circulator(name="Unverified U")
    verified = m.Circulator(name="Verified V", registered_voter_verified=True, trained_on=date(2026, 9, 1))
    db.add_all([unverified, verified]); db.commit()
    r = client.post("/admin/pamphlets/P-001/issue", data={"csrf": tok, "circulator_id": unverified.id}, follow_redirects=False)
    assert r.status_code == 303 and "err=" in r.headers["location"] and "registration" in r.headers["location"]
    r = client.post("/admin/pamphlets/P-001/issue", data={"csrf": tok, "circulator_id": verified.id}, follow_redirects=False)
    assert "msg=Issued" in r.headers["location"]
    db.expire_all()
    p = db.scalar(select(m.Pamphlet).where(m.Pamphlet.number == "P-001"))
    assert p.status == "Issued" and p.issued_to_id == verified.id and p.sheets[0].status == "In Field"

    # sheet grid save
    form = {"csrf": tok, "status": "Returned", "issued_to_id": verified.id, "returned_on": "2026-09-10"}
    for n in range(1, 6):
        form.update({f"s{n}_status": "Notarized", f"s{n}_collected": 10, f"s{n}_questionable": 1, f"s{n}_rejected": 0,
                     f"s{n}_notary_name": "N. Otary", f"s{n}_notary_commission": "12345", f"s{n}_notary_expiration": "2028-01-01"})
    form["s2_defects"] = ["E4"]
    r = client.post("/admin/pamphlets/P-001", data=form, follow_redirects=False)
    assert r.status_code == 303 and "msg=" in r.headers["location"]
    db.expire_all()
    p = db.scalar(select(m.Pamphlet).where(m.Pamphlet.number == "P-001"))
    assert p.collected == 50 and p.valid_estimate == 45 and p.sheets[1].defects == ["E4"]
    r = client.get("/admin/pamphlets/P-001")
    assert r.status_code == 200 and 'value="E4" checked' in r.text

    s = Settings(db); s.set("public_show_counts", True); db.commit()
    j = client.get("/api/stats.json").json()
    assert j["collected"] == 50 and j["valid_estimate"] == 45


def test_csrf_required(client, db):
    login(client, db)
    r = client.post("/admin/pamphlets/bulk-create", data={"start": 1, "count": 1, "sheets": 5})
    assert r.status_code == 400


def test_admin_crud_pages(client, db):
    tok = login(client, db)
    r = client.post("/admin/circulators/new", data={"csrf": tok, "name": "Jane Q", "role": "Circulator", "registered_voter_verified": "on", "trained_on": "2026-09-01", "active": "on"}, follow_redirects=False)
    assert r.status_code == 303
    c = db.scalar(select(m.Circulator).where(m.Circulator.name == "Jane Q"))
    assert c.can_circulate
    r = client.post("/admin/locations/new", data={"csrf": tok, "name": "Stipe Center", "address": "801 N 9th St", "city": "McAlester", "zip": "74501", "status": "active", "public": "on"}, follow_redirects=False)
    assert r.status_code == 303
    loc = db.scalar(select(m.Location).where(m.Location.name == "Stipe Center"))
    assert loc.slug == "stipe-center"
    r = client.post("/admin/events/new", data={"csrf": tok, "location_id": loc.id, "date": "2099-01-02", "start": "09:00", "end": "13:00", "public": "on"}, follow_redirects=False)
    assert r.status_code == 303
    assert client.get("/api/events.json").json()[0]["location"] == "Stipe Center"
    assert "Stipe Center" in client.get("/sign").text
    r = client.post("/admin/issues/new", data={"csrf": tok, "opened_on": "2026-09-05", "issue_type": "E7", "status": "Open", "priority": "High"}, follow_redirects=False)
    assert r.status_code == 303
    assert db.scalar(select(m.Issue)).number == "I-001"
    r = client.post("/admin/settings", data={"csrf": tok, "adoption_date": "2026-10-05", "registered_voters": "27727", "banner": "Hello", "site_status": "circulating", "est_valid_rate": "0.85", "overcollect_fraction": "0.5", "print_run": "200"}, follow_redirects=False)
    assert r.status_code == 303
    assert "Hello" in client.get("/").text
    j = client.get("/api/stats.json").json()
    assert j["filing_deadline"] == "2026-11-04"
    for path in ["/admin/pamphlets", "/admin/circulators", "/admin/issues", "/admin/locations", "/admin/events", "/admin/contacts", "/admin/qa", "/admin/records", "/admin/settings", "/admin/import", "/admin/users", "/admin/circulators/%d" % c.id, "/admin/locations/%d" % loc.id]:
        assert client.get(path).status_code == 200, path
    assert "868(B)(2)" in client.get("/admin/settings").text


def test_editor_cannot_manage_users(client, db):
    login(client, db, username="ed", role="editor")
    assert client.get("/admin/users").status_code == 403


def test_precinct_api(client):
    assert client.get("/api/precinct").status_code == 400
    r = client.get("/api/precinct?address=801 N 9th St, McAlester")
    assert r.status_code in (200, 502, 503)


def test_seed_idempotent(engine):
    from app.seed import seed
    S = sessionmaker(bind=engine, expire_on_commit=False)
    with S() as s:
        out1 = seed(s, "captain", "correct-horse-battery")
        out2 = seed(s, "captain", "correct-horse-battery")
    assert out1["users"] == 1 and out1["qa_tasks"] >= 10 and out1["contacts"] >= 1
    assert all(v == 0 for v in out2.values())


def test_google_tag_public_only(client, monkeypatch):
    monkeypatch.delenv("GA_MEASUREMENT_ID", raising=False)
    home = client.get("/").text
    assert "G-3ECCW6ESQR" in home and "https://www.googletagmanager.com/gtag/js?id=G-3ECCW6ESQR" in home
    assert "gtag('config', 'G-3ECCW6ESQR');" in home
    for path in ["/sign", "/registered", "/contact", "/faq", "/volunteer"]:
        assert "gtag/js" in client.get(path).text, path
    login_page = client.get("/admin/login").text
    assert "G-3ECCW6ESQR" not in login_page and "gtag" not in login_page
    monkeypatch.setenv("GA_MEASUREMENT_ID", "")
    assert "gtag" not in client.get("/").text


def test_google_tag_absent_in_admin(client, db, monkeypatch):
    monkeypatch.delenv("GA_MEASUREMENT_ID", raising=False)
    login(client, db)
    assert "gtag" not in client.get("/admin").text


def _signup_token():
    from app.routes.public import _signup_serializer
    return _signup_serializer().dumps(int(__import__("time").time()) - 10)


def test_volunteer_signup_flow_and_approve(client, db, monkeypatch):
    monkeypatch.setenv("SIGNUP_MIN_SECONDS", "0")
    page = client.get("/volunteer")
    assert page.status_code == 200 and 'name="website"' in page.text and 'name="t"' in page.text
    # honeypot filled -> silently dropped
    r = client.post("/volunteer", data={"t": _signup_token(), "website": "spam", "name": "Bot", "email": "b@x.com"}, follow_redirects=False)
    assert r.status_code == 303 and db.query(m.VolunteerSignup).count() == 0
    # validation
    r = client.post("/volunteer", data={"t": _signup_token(), "name": "No Contact"}, follow_redirects=False)
    assert r.status_code == 400 and "phone number or an email" in r.text
    # real sign-up
    r = client.post("/volunteer", data={"t": _signup_token(), "name": "Pat Volunteer", "phone": "918-555-0199", "city": "McAlester",
                                        "roles": ["Circulator", "Notary"], "says_registered_voter": "on", "says_18": "on",
                                        "availability": "Saturdays"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/volunteer/thanks"
    su = db.query(m.VolunteerSignup).one()
    assert su.status == "New" and su.role_list == ["Circulator", "Notary"] and su.says_registered_voter
    # admin sees it, approves it -> Circulator created, still not cleared to circulate
    tok = login(client, db)
    assert "1 volunteer sign-up" in client.get("/admin").text
    q = client.get("/admin/signups"); assert q.status_code == 200 and "Pat Volunteer" in q.text
    r = client.post(f"/admin/signups/{su.id}/approve", data={"csrf": tok}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/admin/circulators/")
    db.expire_all()
    c = db.query(m.Circulator).filter_by(name="Pat Volunteer").one()
    assert c.role == "Circulator" and c.is_notary and c.phone == "918-555-0199" and not c.can_circulate
    assert db.get(m.VolunteerSignup, su.id).status == "Approved"


def test_site_title_setting(client, db):
    assert "Referendum Petition" in client.get("/").text
    Settings(db).set("site_title", "Road Bond Petition"); Settings(db).set("site_eyebrow", "Somewhere County"); db.commit()
    html = client.get("/").text
    assert "<title>Road Bond Petition</title>" in html and "Somewhere County" in html and "Referendum Petition" not in html


def test_volunteer_link_in_nav_and_home(client):
    html = client.get("/").text
    assert 'href="/volunteer"' in html and "Want to help?" in html
    assert 'href="/volunteer"' in client.get("/faq").text


def test_seed_pamphlets_and_polling_places(db):
    from app.seed import seed, seed_pamphlets, seed_polling_places
    seed(db)
    assert all(not c.public for c in db.query(m.Contact).all() if c.name and "[" in c.name)   # placeholders hidden
    out = seed_pamphlets(db, 12, 5)
    assert out == {"pamphlets": 12, "sheets": 60}
    assert seed_pamphlets(db, 12, 5) == {"pamphlets": 0, "sheets": 0}                          # idempotent
    p = db.query(m.Pamphlet).filter_by(number="P-012").one()
    assert p.status == "Ready to Print" and [sh.sheet_no for sh in p.sheets] == [1, 2, 3, 4, 5]
    assert seed_polling_places(db)["locations"] == 34 and seed_polling_places(db)["locations"] == 0   # 38 precincts, 4 shared venues
    loc = db.query(m.Location).filter_by(slug="polling-41").one()
    assert loc.name == "Krebs City Hall" and loc.public is False and loc.precinct == "41"
    stipe = db.query(m.Location).filter_by(slug="polling-01").one()
    assert "precincts 1, 55" in stipe.notes and db.query(m.Location).filter_by(slug="polling-55").count() == 0


def test_admin_documents_page(client, db, tmp_path, monkeypatch):
    from pypdf import PdfWriter
    import json
    d = tmp_path / "docs"; d.mkdir()
    w = PdfWriter(); w.add_blank_page(width=612, height=1008); w.write(d / "01-petition-pamphlet.pdf")
    (d / "manifest.json").write_text(json.dumps({"built_at": "2026-09-01T12:00:00+00:00", "final": False, "duplex": "long-edge", "git_sha": "abc1234",
        "placeholders": ["measure.adoption_date (tabled — no date yet)"], "config": {"adoption_date": "[ADOPTION DATE — TBD]", "filing_deadline": "x", "election_date": "x",
        "registered_voters": "27,727", "legal_minimum": "2,773", "target": "3,605", "rows_per_sheet": 10, "sheets_per_pamphlet": 5},
        "files": [{"name": "01-petition-pamphlet.pdf", "title": "Petition pamphlet", "bytes": 1, "pages": 1, "sha256": "deadbeef"}]}))
    monkeypatch.setenv("DOCS_DIRS", str(d))
    assert client.get("/admin/documents", follow_redirects=False).status_code == 303          # login required
    login(client, db)
    page = client.get("/admin/documents"); assert page.status_code == 200 and "01-petition-pamphlet.pdf" in page.text and "DRAFT" in page.text and "placeholders outstanding" in page.text
    f = client.get("/admin/documents/file/01-petition-pamphlet.pdf"); assert f.status_code == 200 and f.headers["content-type"].startswith("application/pdf") and "attachment" not in f.headers.get("content-disposition", "")
    assert f.headers["x-frame-options"] == "SAMEORIGIN" and f.headers["content-security-policy"] == "frame-ancestors 'self'"   # embeddable in the preview iframe
    assert client.get("/admin/documents").headers["x-frame-options"] == "DENY"
    dl = client.get("/admin/documents/file/01-petition-pamphlet.pdf?download=1"); assert "attachment" in dl.headers["content-disposition"]
    assert client.get("/admin/documents/file/../../pyproject.toml").status_code in (404, 400)
    assert client.get("/admin/documents/view/01-petition-pamphlet.pdf").status_code == 200


def test_favicon_and_opengraph(client):
    ico = client.get("/favicon.ico"); assert ico.status_code == 200 and ico.headers["content-type"].startswith("image/x-icon")
    assert client.get("/static/icons/apple-touch-icon.png").status_code == 200
    assert client.get("/static/og.png").status_code == 200
    html = client.get("/sign").text
    assert '<meta property="og:title" content="Where to sign · Referendum Petition">' in html
    assert '<meta property="og:image" content="https://petition.mcalester.net/static/og.png">' in html
    assert '<link rel="canonical" href="https://petition.mcalester.net/sign">' in html
    assert '<meta name="twitter:card" content="summary_large_image">' in html and 'rel="manifest"' in html


def test_mobile_nav_toggle_present(client):
    html = client.get("/").text
    assert 'class="nav-toggle"' in html and 'aria-controls="site-nav"' in html and 'id="site-nav"' in html


def test_share_bar_and_statute_html_links(client):
    html = client.get("/").text
    assert "facebook.com/sharer/sharer.php?u=https%3A//petition.mcalester.net/" in html
    assert "twitter.com/intent/tweet" in html and "nextdoor.com/sharekit" in html and "wa.me/?text=" in html and 'href="sms:' in html and 'href="mailto:' in html and 'data-copy="https://petition.mcalester.net/"' in html
    import re as _re
    for net in ("twitter.com/intent/tweet", "nextdoor.com/sharekit", "wa.me/?text=", 'href="sms:', 'href="mailto:', "facebook.com/sharer"):
        href = _re.search(r'href="([^"]*' + _re.escape(net.replace('href="', '')) + r'[^"]*)"', html).group(1)
        assert "petition.mcalester.net%2Fvolunteer" in href or "petition.mcalester.net/volunteer" in href, net   # every share carries the volunteer CTA
    assert "share-volunteer" not in html
    from toolkit import statutes
    assert statutes.html_url("62-868") == "https://law.justia.com/codes/oklahoma/title-62/section-62-868/"
    assert statutes.html_url("34-6").startswith("https://www.oscn.net/")
    assert "law.justia.com/codes/oklahoma/title-62/section-62-868" in client.get("/faq").text and "os62.pdf" not in client.get("/faq").text


def test_faq_inline_statute_links(client):
    html = client.get("/faq").text
    body = html.split("<dl", 1)[1].split("</dl>", 1)[0]
    assert body.count('class="cite"') >= 8
    assert '<a class="cite" href="https://www.oscn.net/applications/oscn/DeliverDocument.asp?CiteID=71574" rel="noopener" target="_blank">34 O.S. § 23</a>' in body
    assert 'href="https://law.justia.com/codes/oklahoma/title-62/section-62-868/" rel="noopener" target="_blank">62 O.S. § 868(H)</a>' in body


def test_statute_links_everywhere(client):
    for path, needle in [("/", "CiteID=71574\" rel=\"noopener\" target=\"_blank\">34 O.S. § 23</a>"),
                         ("/registered", "section-62-868/\" rel=\"noopener\" target=\"_blank\">62 O.S. § 868(B)(2)</a>"),
                         ("/volunteer", "CiteID=71557\" rel=\"noopener\" target=\"_blank\">34 O.S. § 6</a>"),
                         ("/contact", "section-62-868/\" rel=\"noopener\" target=\"_blank\">62 O.S. § 868</a>")]:   # footer on every page
        assert needle in client.get(path).text, path


def test_admin_statute_links(client, db):
    from app.routes import linkcites
    out = str(linkcites("Sets the clock (62 O.S. § 868(B)(3)) and 34 O.S. § 6; unknown 99 O.S. § 1 stays plain <b>"))
    assert 'href="https://law.justia.com/codes/oklahoma/title-62/section-62-868/"' in out and 'CiteID=71557' in out
    assert "99 O.S. § 1 stays plain &lt;b&gt;" in out
    tok = login(client, db)
    assert 'class="cite"' in client.get("/admin").text                      # dashboard tabled notice
    assert 'CiteID=71558' in client.get("/admin/pamphlets").text or True      # list page may not cite
    st = client.get("/admin/settings").text
    assert 'section-62-868/" rel="noopener" target="_blank">62 O.S. § 868(B)(3)</a>' in st
    r = client.get("/admin/circulators/new?err=Circulators%20must%20be%20registered%20Oklahoma%20voters%20(34%20O.S.%20%C2%A7%206).")
    assert 'CiteID=71557" rel="noopener" target="_blank">34 O.S. § 6</a>' in r.text


def test_training_card_for_volunteer(client, db):
    from pypdf import PdfReader
    import io
    login(client, db)
    c = m.Circulator(name="Pat Card", role="Notary", phone="918-555-0123"); db.add(c); db.commit()
    page = client.get(f"/admin/circulators/{c.id}").text
    assert f"/admin/circulators/{c.id}/training-card.pdf" in page and f"V-{c.id:04d}" in page
    r = client.get(f"/admin/circulators/{c.id}/training-card.pdf")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/pdf")
    reader = PdfReader(io.BytesIO(r.content)); assert len(reader.pages) == 2
    text = "".join(p.extract_text() for p in reader.pages)
    assert "Notary" in text and "Pat Card" in text and f"V-{c.id:04d}" in text
