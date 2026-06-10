"""Tests for sdr/resolve.py — entity resolution gate."""
from sdr.resolve import resolve_lead


def _fetcher(pages: dict):
    def fetch(url: str) -> str:
        return pages.get(url, "")
    return fetch


def test_verified_when_name_on_site():
    lead = {"name": "Acme Dental Studio", "domain": "acmedental.com", "location": "Austin, TX"}
    fetch = _fetcher({"https://acmedental.com": "<h1>Welcome to Acme Dental Studio</h1>"})
    out = resolve_lead(lead, fetch=fetch)
    assert out["resolution"] == "verified"


def test_weak_when_partial_match():
    lead = {"name": "Acme Dental Studio", "domain": "acmedental.com", "location": "Austin, TX"}
    fetch = _fetcher({"https://acmedental.com": "Best dental care in Austin"})
    out = resolve_lead(lead, fetch=fetch)
    assert out["resolution"] == "weak"


def test_unresolved_no_domain():
    out = resolve_lead({"name": "Acme", "domain": ""}, fetch=_fetcher({}))
    assert out["resolution"] == "unresolved"
    assert "domain" in out["reason"]


def test_unresolved_fetch_fails():
    lead = {"name": "Acme Dental", "domain": "dead.example"}
    out = resolve_lead(lead, fetch=_fetcher({}))   # fetch returns ""
    assert out["resolution"] == "unresolved"


def test_unresolved_wrong_site():
    lead = {"name": "Acme Dental Studio", "domain": "acmedental.com", "location": ""}
    fetch = _fetcher({"https://acmedental.com": "Buy cheap domains here!"})
    assert resolve_lead(lead, fetch=fetch)["resolution"] == "unresolved"
