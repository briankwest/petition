from datetime import date
import pytest
from toolkit import config, statutes


def test_load_placeholders_present():
    p = config.load()
    assert p.county == "Pittsburg"
    assert p.measure.adoption_date is None and p.filing_deadline is None
    assert p.threshold.registered_voters == 27727 and p.legal_minimum == 2773 and p.target_signatures == 4437
    assert p.threshold.registered_voters_active + p.threshold.registered_voters_inactive == p.threshold.registered_voters
    assert "threshold.registered_voters" not in p.placeholders
    assert "measure.adoption_date (tabled — no date yet)" in p.placeholders
    assert not p.is_final_ready
    assert "TBD" in p.fmt.adoption_date and "TBD" in p.fmt.filing_deadline
    assert config.PLACEHOLDER_RE.search(p.fmt.resolution_number)


def test_derived_math(tmp_path):
    import yaml
    raw = yaml.safe_load(open(config.DEFAULT_PATH))
    raw["measure"]["adoption_date"] = "2026-10-05"
    raw["threshold"]["registered_voters"] = 27590
    f = tmp_path / "p.yaml"; f.write_text(yaml.safe_dump(raw))
    p = config.load(f)
    assert p.filing_deadline == date(2026, 11, 4)          # +30 days, § 868(B)(3)
    assert p.legal_minimum == 2759                          # ceil(10%), § 868(B)(2)
    assert p.target_signatures == 4415                      # ceil(16%)
    assert p.fmt.filing_deadline == "November 4, 2026"


def test_ballot_title_within_868_limit():
    p = config.load()
    assert p.ballot_title_word_count <= 150
    assert "YES vote" in p.ballot_title and "NO vote" in p.ballot_title


def test_statute_fragments():
    w = statutes.warning_sentence()
    assert w.startswith("It is a felony") and w.endswith("legal voter of this state.")
    ex = statutes.exclusions()
    assert len(ex) == 8 and "notary" in ex[6]
    a = statutes.affidavit("Pittsburg")
    assert "county of Pittsburg" in a["body"]
    n = statutes.statutory_numbers()
    assert n == {"county_fraction": 0.10, "referendum_days": 30, "protest_days": 10,
                 "ballot_title_words": 150, "da_review_days": 3, "warning_min_pt": 10}


def test_config_matches_statute_numbers():
    p, n = config.load(), statutes.statutory_numbers()
    assert p.threshold.legal_fraction == n["county_fraction"]
    assert p.deadlines.filing_days_after_adoption == n["referendum_days"]
    assert p.deadlines.protest_days_after_publication == n["protest_days"]
    assert p.deadlines.ballot_title_da_review_days == n["da_review_days"]
    assert p.layout.warning_pt >= n["warning_min_pt"]
