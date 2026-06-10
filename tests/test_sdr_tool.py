"""Wire-up tests: manager tool present, sample CSV loads."""
from sdr.ingest import load_leads


def test_scan_leads_in_manager_tools():
    from orchestrator.tools import MANAGER_TOOLS, scan_leads  # noqa: F401
    assert any(getattr(t, "__name__", "") == "scan_leads" for t in MANAGER_TOOLS)


def test_sample_leads_csv_loads():
    rows = load_leads("data/leads.csv")
    assert len(rows) >= 5
    assert all(r["domain"] for r in rows)   # demo CSV must carry domains for resolution
