from datetime import date
import pytest
from sqlalchemy.orm import sessionmaker
from app.db import Base, make_engine
from app import models
from app.settings import Settings
from app.stats import signature_stats


@pytest.fixture
def db():
    eng = make_engine("sqlite://")
    Base.metadata.create_all(eng)
    S = sessionmaker(bind=eng, expire_on_commit=False)
    with S() as s:
        yield s


def test_settings_defaults_and_math(db):
    s = Settings(db)
    assert s.adoption_date is None and s.filing_deadline is None
    assert s.registered_voters == 27727 and s.legal_minimum == 2773      # config fallback (total registered)
    assert "tabled" in s.raw("banner")
    s.set("adoption_date", date(2026, 10, 5)); s.set("registered_voters", 27590); db.commit()
    s = Settings(db)                                                      # DB row overrides config
    assert s.filing_deadline == date(2026, 11, 4)
    assert s.legal_minimum == 2759 and s.target_signatures == 3587   # overcollect default = 13%/10% - 1 = 0.3


def test_stats_roll_up(db):
    c = models.Circulator(name="A", registered_voter_verified=True, trained_on=date(2026, 9, 1)); db.add(c)
    p = models.Pamphlet(number="P-001", status="Returned", issued_to=c)
    p.sheets = [models.Sheet(sheet_no=i, status="Notarized", collected=10, questionable=1, rejected=0) for i in range(1, 6)]
    db.add(p); db.add(models.Pamphlet(number="P-002")); db.add(models.Issue(number="I-001", status="Open", issue_type="E7"))
    db.commit()
    st = signature_stats(db, Settings(db))
    assert st["collected"] == 50 and st["valid_estimate"] == 45 and st["est_valid"] == 38
    assert st["pamphlets"]["Returned"] == 1 and st["pamphlets"]["Ready to Print"] == 1
    assert st["sheets"]["Notarized"] == 5 and st["open_issues"] == 1 and st["circulators_ready"] == 1
    assert p.collected == 50 and p.notarized_sheets == 5 and p.sheets[0].sheet_id == "P-001-S1"
    assert c.can_circulate
