"""Tests for sdr/ingest.py."""
import pytest

from sdr.ingest import ingest_csv, load_leads
from sdr.store import SdrStore

CSV = """name,domain,linkedin_url,location,services,contact_name,contact_email,last_service,deal_value,status
Acme Dental,acmedental.com,https://linkedin.com/company/acme,"Austin, TX",dental,Dr. A,a@acme.com,SEO,12000,past
,missing.com,,,,,,,
Bare Lead,,,,,,,,,
"""


def test_load_leads_tolerant(tmp_path):
    p = tmp_path / "leads.csv"
    p.write_text(CSV)
    rows = load_leads(p)
    assert len(rows) == 2                       # blank-name row skipped
    assert rows[0]["name"] == "Acme Dental"
    assert rows[0]["deal_value"] == 12000.0     # numeric coercion
    assert rows[1]["name"] == "Bare Lead"
    assert rows[1]["domain"] == ""              # optionals default to empty


def test_load_leads_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_leads(tmp_path / "nope.csv")


def test_ingest_csv_upserts_and_creates_batch(tmp_path):
    p = tmp_path / "leads.csv"
    p.write_text(CSV)
    store = SdrStore(":memory:")
    out = ingest_csv(store, p)
    assert out["batch_id"] >= 1
    assert len(out["leads"]) == 2
    assert store.get_batch(out["batch_id"])["total"] == 2
    again = ingest_csv(store, p)                # re-upload: same leads, new batch
    assert len(store.list_leads()) == 2
    assert again["batch_id"] != out["batch_id"]


# --- save_leads_text (chat-pasted leads) ---


def test_save_leads_text_creates_file(tmp_path):
    from sdr.ingest import save_leads_text
    out = save_leads_text(
        "name,domain,contact_email\nAcme Dental,acmedental.com,a@acme.com\n",
        tmp_path / "leads.csv")
    assert out["imported"] == 1 and out["total_in_file"] == 1
    rows = load_leads(tmp_path / "leads.csv")
    assert rows[0]["name"] == "Acme Dental"
    assert rows[0]["domain"] == "acmedental.com"


def test_save_leads_text_appends_and_dedupes(tmp_path):
    from sdr.ingest import save_leads_text
    p = tmp_path / "leads.csv"
    save_leads_text("name,domain\nAcme,acme.com\n", p)
    out = save_leads_text("name,domain\nAcme,acme.com\nNewCo,newco.com\n", p)
    assert out["imported"] == 1                      # Acme deduped, NewCo added
    assert out["total_in_file"] == 2


def test_save_leads_text_replace(tmp_path):
    from sdr.ingest import save_leads_text
    p = tmp_path / "leads.csv"
    save_leads_text("name,domain\nOld,old.com\n", p)
    out = save_leads_text("name,domain\nNew,new.com\n", p, replace=True)
    assert out["total_in_file"] == 1
    assert load_leads(p)[0]["name"] == "New"


def test_save_leads_text_rejects_garbage(tmp_path):
    import pytest as _pytest
    from sdr.ingest import save_leads_text
    with _pytest.raises(ValueError):
        save_leads_text("", tmp_path / "x.csv")
    with _pytest.raises(ValueError):
        save_leads_text("not,a,header\n1,2,3\n", tmp_path / "x.csv")
