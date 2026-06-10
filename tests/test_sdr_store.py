"""Tests for sdr/store.py — the SDR ledger."""
from sdr.store import SdrStore


def test_upsert_and_get_lead():
    s = SdrStore(":memory:")
    lead = s.upsert_lead({"name": "Acme Dental", "domain": "acmedental.com",
                          "contact_email": "a@acme.com"})
    assert lead["id"] >= 1
    assert lead["resolution"] == "unresolved"
    again = s.upsert_lead({"name": "Acme Dental", "domain": "acmedental.com",
                           "location": "Austin, TX"})
    assert again["id"] == lead["id"]          # same identity → same row
    assert again["location"] == "Austin, TX"  # fields merged
    assert len(s.list_leads()) == 1


def test_set_resolution():
    s = SdrStore(":memory:")
    lead = s.upsert_lead({"name": "X", "domain": "x.com"})
    s.set_resolution(lead["id"], "verified")
    assert s.get_lead(lead["id"])["resolution"] == "verified"


def test_add_point_detects_change():
    s = SdrStore(":memory:")
    lead = s.upsert_lead({"name": "X", "domain": "x.com"})
    first = s.add_point(lead["id"], "website:home", "hello world", "website", "verified", "")
    assert first["changed"] is False          # first sighting = baseline, not a change
    same = s.add_point(lead["id"], "website:home", "hello world", "website", "verified", "")
    assert same["changed"] is False
    diff = s.add_point(lead["id"], "website:home", "new clinic!", "website", "verified", "")
    assert diff["changed"] is True
    assert s.latest_point(lead["id"], "website:home")["value"] == "new clinic!"


def test_add_signal_dedupes():
    s = SdrStore(":memory:")
    lead = s.upsert_lead({"name": "X", "domain": "x.com"})
    sig = s.add_signal(lead["id"], "expansion", "opened in Frisco", "verified",
                       "high", "Local SEO", 7.5)
    assert sig is not None and sig["state"] == "new"
    dup = s.add_signal(lead["id"], "expansion", "opened in Frisco", "verified",
                       "high", "Local SEO", 7.5)
    assert dup is None                        # same lead+type+summary → no repost
    assert len(s.list_signals()) == 1
    s.set_signal_state(sig["id"], "posted")
    assert s.list_signals(state="posted")[0]["id"] == sig["id"]


def test_batches():
    s = SdrStore(":memory:")
    bid = s.create_batch("data/leads.csv", total=10)
    s.finish_batch(bid, resolved=8, signals_found=3, errors=1)
    b = s.get_batch(bid)
    assert b["total"] == 10 and b["signals_found"] == 3 and b["finished_at"]
