"""Wire-up tests: manager tool present, sample CSV loads."""
from sdr.ingest import load_leads


def test_scan_leads_in_manager_tools():
    from orchestrator.tools import MANAGER_TOOLS, scan_leads  # noqa: F401
    assert any(getattr(t, "__name__", "") == "scan_leads" for t in MANAGER_TOOLS)


def test_sample_leads_csv_loads():
    rows = load_leads("data/leads.csv")
    assert len(rows) >= 5
    assert all(r["domain"] for r in rows)   # demo CSV must carry domains for resolution


def test_import_leads_tool_roundtrip(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    from orchestrator.tools import MANAGER_TOOLS, import_leads
    assert any(getattr(t, "__name__", "") == "import_leads" for t in MANAGER_TOOLS)
    out = import_leads("name,domain\nAcme,acme.com\n")
    assert out["ok"] is True and out["imported"] == 1
    bad = import_leads("just some prose, not csv")
    assert bad["ok"] is False and "header" in bad["error"]


def test_set_offers_roundtrip(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from orchestrator.tools import list_offers, set_offers
    out = set_offers([
        {"name": "Web Design Retainer", "triggers": ["website", "redesign"]},
        {"name": "AI Receptionist", "triggers": ["hiring", "front desk"]},
        {"name": ""},                       # invalid, skipped
    ])
    assert out["ok"] is True
    assert out["offers_saved"] == ["Web Design Retainer", "AI Receptionist"]
    # the matcher actually uses the new catalog
    from sdr.offers import load_offers, match_offer
    offers = load_offers("data/offers.json")
    assert match_offer("expansion", "they are hiring a front desk person", offers) \
        == "AI Receptionist"
    assert len(list_offers()["offers"]) == 2


def test_set_offers_rejects_empty(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from orchestrator.tools import set_offers
    assert set_offers([])["ok"] is False
