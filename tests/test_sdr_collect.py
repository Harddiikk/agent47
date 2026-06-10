"""Tests for sdr/collect.py."""
from sdr.collect import collect_grounded, collect_website, diff_excerpt
from sdr.store import SdrStore


def _fetcher(pages: dict):
    return lambda url: pages.get(url, "")


def test_first_scan_is_baseline_not_change():
    store = SdrStore(":memory:")
    lead = store.upsert_lead({"name": "Acme", "domain": "acme.com"})
    fetch = _fetcher({"https://acme.com": "Welcome. Two locations."})
    out = collect_website(lead, store, fetch=fetch)
    assert out["changes"] == []                       # baseline stored, nothing "new"
    assert store.latest_point(lead["id"], "website:home")


def test_rescan_detects_change_with_excerpt():
    store = SdrStore(":memory:")
    lead = store.upsert_lead({"name": "Acme", "domain": "acme.com"})
    collect_website(lead, store, fetch=_fetcher({"https://acme.com": "Welcome. Two locations."}))
    out = collect_website(
        lead, store,
        fetch=_fetcher({"https://acme.com": "Welcome. Two locations. Now open in Frisco!"}))
    assert len(out["changes"]) == 1
    chg = out["changes"][0]
    assert chg["field"] == "website:home"
    assert "Frisco" in chg["excerpt"]


def test_no_domain_skips_quietly():
    store = SdrStore(":memory:")
    lead = store.upsert_lead({"name": "Acme", "domain": ""})
    out = collect_website(lead, store, fetch=_fetcher({}))
    assert out["changes"] == [] and out["pages_seen"] == 0


def test_diff_excerpt_returns_new_sentences():
    old, new = "We are great. Call us.", "We are great. Call us. New laser machine arrived."
    assert "laser" in diff_excerpt(old, new)
    assert diff_excerpt(old, old) == ""


def test_collect_grounded_delegates():
    fake = lambda name, location="", services="": {"has_signal": True, "name": name}  # noqa: E731
    out = collect_grounded({"name": "Acme", "location": "TX", "services": "dental"},
                           research_fn=fake)
    assert out == {"has_signal": True, "name": "Acme"}
