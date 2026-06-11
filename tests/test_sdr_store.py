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


def test_has_recent_signal_cooldown():
    s = SdrStore(":memory:")
    lead = s.upsert_lead({"name": "X", "domain": "x.com"})
    assert s.has_recent_signal(lead["id"], "expansion") is False
    s.add_signal(lead["id"], "expansion", "opened in Frisco", "verified",
                 "high", "Local SEO", 7.5)
    assert s.has_recent_signal(lead["id"], "expansion") is True    # same type → cooldown
    assert s.has_recent_signal(lead["id"], "update") is False      # other type → free


def test_store_is_thread_safe():
    """Concurrent workers hammer one :memory: store — must not raise or lose writes."""
    from concurrent.futures import ThreadPoolExecutor

    s = SdrStore(":memory:")
    lead = s.upsert_lead({"name": "X", "domain": "x.com"})

    def work(i: int):
        s.add_point(lead["id"], f"f{i}", f"v{i}", "website", "verified", "")
        s.add_signal(lead["id"], "expansion", f"signal {i}", "verified", "low", "o", 1.0)
        s.latest_point(lead["id"], f"f{i}")
        s.has_recent_signal(lead["id"], "expansion")

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(work, range(60)))

    assert len(s.list_signals()) == 60


def test_upsert_lead_survives_cross_instance_race(tmp_path):
    """Two store instances (two requests) upserting the same lead concurrently
    must never raise IntegrityError and must end with exactly one row."""
    from concurrent.futures import ThreadPoolExecutor

    db = tmp_path / "race.db"
    a, b = SdrStore(db), SdrStore(db)   # separate instances = separate locks

    def hammer(store):
        for _ in range(40):
            store.upsert_lead({"name": "Milan Laser", "domain": "milanlaser.com"})

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(hammer, [a, b]))   # raises if IntegrityError escapes

    assert len(SdrStore(db).list_leads()) == 1


def test_upsert_never_rewrites_identity_or_collides(tmp_path):
    """Regression: raw-cased domains written back by updates created near-dupe
    rows whose later updates hit the UNIQUE constraint (prod IntegrityError)."""
    db = tmp_path / "dirty.db"
    s = SdrStore(db)
    clean = s.upsert_lead({"name": "Acme Dental", "domain": "acme.com"})
    # simulate legacy dirty row from the old behavior (trailing space in name)
    con = s._conn()
    con.execute(
        "INSERT INTO leads (name, domain, linkedin_url, location, services, "
        "contact_name, contact_email, last_service, deal_value, status, "
        "created_at, updated_at) VALUES ('Acme Dental ', 'acme.com', '', '', "
        "'', '', '', '', 0, '', 'x', 'x')")
    con.commit()
    con.close()
    # this upsert used to rewrite name to the raw 'Acme Dental ' and collide
    out = s.upsert_lead({"name": "Acme Dental", "domain": "ACME.com",
                         "location": "Austin"})
    assert out["id"] == clean["id"]
    assert out["name"] == "Acme Dental"      # identity untouched
    assert out["domain"] == "acme.com"        # stays normalized
    assert out["location"] == "Austin"        # enrichment still lands
