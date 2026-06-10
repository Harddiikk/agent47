"""Tests for sdr/verify.py — confidence-tier decisions."""
from sdr.verify import verify_grounded

VERDICT = {
    "has_signal": True, "signal_type": "expansion", "severity": "high",
    "summary": "Acme opened a new Frisco clinic in March 2026",
    "evidence": [{"claim": "new Frisco clinic", "source_url": "https://news.com/a"}],
    "confidence": 0.9,
}


def test_verified_when_corroborated_and_fresh():
    fetch = lambda url: "Acme announces new Frisco clinic opening March 2026"  # noqa: E731
    assert verify_grounded(VERDICT, fetch=fetch, today_year=2026) == "verified"


def test_probable_when_fetchable_but_uncorroborated():
    fetch = lambda url: "totally unrelated page content here"  # noqa: E731
    assert verify_grounded(VERDICT, fetch=fetch, today_year=2026) == "probable"


def test_discard_when_evidence_unfetchable():
    assert verify_grounded(VERDICT, fetch=lambda url: "", today_year=2026) == "discard"


def test_discard_when_stale():
    old = {**VERDICT, "summary": "Acme opened a clinic in 2021"}
    fetch = lambda url: "Acme opened a clinic in 2021"  # noqa: E731
    assert verify_grounded(old, fetch=fetch, today_year=2026) == "discard"


def test_discard_when_no_evidence():
    assert verify_grounded({**VERDICT, "evidence": []}, fetch=lambda u: "x") == "discard"
