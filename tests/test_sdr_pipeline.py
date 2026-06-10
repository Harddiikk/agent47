"""End-to-end pipeline test — every external surface faked."""
from sdr.pipeline import run_scan
from sdr.store import SdrStore

CSV = """name,domain,location,services,contact_name,contact_email
Acme Dental,acmedental.com,"Austin, TX",dental,Dr. A,a@acme.com
Ghost Co,,,,,
"""

SITE = "Welcome to Acme Dental in Austin"
VERDICT = {
    "has_signal": True, "signal_type": "expansion", "severity": "high",
    "summary": "Acme Dental opened a second location in Frisco in 2026",
    "evidence": [{"claim": "second location", "source_url": "https://news.com/a"}],
    "confidence": 0.9, "error": "",
}


def _fetch(url):
    if "acmedental.com" in url:
        return SITE
    if "news.com" in url:
        return "acme dental opened a second location in frisco 2026"
    return ""


def test_run_scan_end_to_end(tmp_path, monkeypatch):
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    csv = tmp_path / "leads.csv"
    csv.write_text(CSV)
    store = SdrStore(":memory:")
    out = run_scan(
        csv, store=store, fetch=_fetch,
        research_fn=lambda n, l="", s="": dict(VERDICT),
        draft_fn=lambda c, s: f"Draft for {c['name']}",
    )
    assert out["total"] == 2
    assert out["resolved"] == 1                      # Ghost Co has no domain
    assert out["unresolved"] == 1
    assert out["signals_found"] == 1
    assert out["delivery"]["mode"] == "formatted"
    sig = store.list_signals()[0]
    assert sig["tier"] == "verified"                 # corroborated + fresh
    assert sig["matched_offer"]
    assert out["top"][0]["name"] == "Acme Dental"


def test_rescan_posts_nothing_new(tmp_path, monkeypatch):
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    csv = tmp_path / "leads.csv"
    csv.write_text(CSV)
    store = SdrStore(":memory:")
    kwargs = dict(store=store, fetch=_fetch,
                  research_fn=lambda n, l="", s="": dict(VERDICT),
                  draft_fn=lambda c, s: "d")
    run_scan(csv, **kwargs)
    second = run_scan(csv, **kwargs)                 # same data → same sig_hash
    assert second["signals_found"] == 0              # deduped, never reposted
    assert len(store.list_signals()) == 1


def test_research_error_counted_not_fatal(tmp_path, monkeypatch):
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    csv = tmp_path / "leads.csv"
    csv.write_text(CSV)
    out = run_scan(csv, store=SdrStore(":memory:"), fetch=_fetch,
                   research_fn=lambda n, l="", s="": {"has_signal": False,
                                                      "error": "503 throttled"},
                   draft_fn=lambda c, s: "d")
    assert out["errors"] >= 1
    assert out["signals_found"] == 0


def test_reworded_grounded_signal_suppressed_by_cooldown(tmp_path, monkeypatch):
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    csv = tmp_path / "leads.csv"
    csv.write_text(CSV)
    store = SdrStore(":memory:")
    v1 = dict(VERDICT)
    v2 = {**VERDICT, "summary": "Acme Dental keeps growing with another brand-new "
                                "office launched in Frisco during 2026"}
    run_scan(csv, store=store, fetch=_fetch,
             research_fn=lambda n, l="", s="": v1, draft_fn=lambda c, s: "d")
    second = run_scan(csv, store=store, fetch=_fetch,
                      research_fn=lambda n, l="", s="": v2, draft_fn=lambda c, s: "d")
    assert second["signals_found"] == 0          # same type, reworded → cooldown holds
    assert len(store.list_signals()) == 1


def test_website_noise_without_trigger_keyword_not_pitched(tmp_path, monkeypatch):
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    csv = tmp_path / "leads.csv"
    csv.write_text(CSV)
    store = SdrStore(":memory:")
    no_sig = {"has_signal": False, "error": ""}
    pages = {"first": "Acme Dental. We love teeth. Our staff rocks today",
             "second": "Acme Dental. We love teeth. Our motto changed completely"}
    state = {"v": "first"}
    fetchers = lambda url: pages[state["v"]] if "acmedental.com" in url else ""  # noqa: E731
    run_scan(csv, store=store, fetch=fetchers,
             research_fn=lambda n, l="", s="": no_sig, draft_fn=lambda c, s: "d")
    state["v"] = "second"
    out = run_scan(csv, store=store, fetch=fetchers,
                   research_fn=lambda n, l="", s="": no_sig, draft_fn=lambda c, s: "d")
    assert out["signals_found"] == 0     # diff exists but has no offer-trigger keyword
