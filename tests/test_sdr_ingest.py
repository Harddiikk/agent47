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


# --- intelligent header mapping ---


def test_save_leads_text_maps_common_crm_headers(tmp_path):
    from sdr.ingest import save_leads_text
    csv_text = (
        "First name,Last name,Company,Website,Email,City\n"
        "Raj,Patel,Smile Dental,smiledental.com,raj@smiledental.com,Austin\n"
    )
    out = save_leads_text(csv_text, tmp_path / "l.csv")
    assert out["imported"] == 1
    row = load_leads(tmp_path / "l.csv")[0]
    assert row["name"] == "Smile Dental"            # Company → name
    assert row["domain"] == "smiledental.com"       # Website → domain
    assert row["contact_name"] == "Raj Patel"       # First+Last → contact_name
    assert row["contact_email"] == "raj@smiledental.com"
    assert row["location"] == "Austin"


def test_save_leads_text_person_only_falls_back(tmp_path):
    from sdr.ingest import save_leads_text
    out = save_leads_text("First name,Last name,Email\nRaj,Patel,r@x.com\n",
                          tmp_path / "l.csv")
    assert out["imported"] == 1
    assert "person name" in out["note"]
    assert load_leads(tmp_path / "l.csv")[0]["name"] == "Raj Patel"


def test_save_leads_text_explicit_column_map_wins(tmp_path):
    from sdr.ingest import save_leads_text
    out = save_leads_text(
        "Biz,WebAddr\nAcme Clinic,acme.com\n",
        tmp_path / "l.csv",
        column_map={"Biz": "name", "WebAddr": "domain"})
    row = load_leads(tmp_path / "l.csv")[0]
    assert out["imported"] == 1
    assert row["name"] == "Acme Clinic" and row["domain"] == "acme.com"


def test_save_leads_text_deal_value_currency_cleaned(tmp_path):
    from sdr.ingest import save_leads_text
    save_leads_text("Company,Deal Value\nAcme,\"$12,500\"\n", tmp_path / "l.csv")
    assert load_leads(tmp_path / "l.csv")[0]["deal_value"] == 12500.0


def test_save_leads_text_unmappable_lists_headers(tmp_path):
    import pytest as _pytest
    from sdr.ingest import save_leads_text
    with _pytest.raises(ValueError) as e:
        save_leads_text("foo,bar\n1,2\n", tmp_path / "l.csv")
    assert "foo" in str(e.value) and "column_map" in str(e.value)


def test_underscore_and_hyphen_headers_map(tmp_path):
    """Regression: 'company_name' and 'full_name' (underscores) failed to map
    and the agent told the founder to rename their spreadsheet columns."""
    from sdr.ingest import save_leads_text
    csv_text = ("company_name,full_name,Email,Company-Website,deal_value\n"
                "Smile Dental,Raj Patel,raj@smile.com,smiledental.com,\"$5,000\"\n")
    out = save_leads_text(csv_text, tmp_path / "l.csv")
    assert out["imported"] == 1
    row = load_leads(tmp_path / "l.csv")[0]
    assert row["name"] == "Smile Dental"
    assert row["contact_name"] == "Raj Patel"
    assert row["contact_email"] == "raj@smile.com"
    assert row["domain"] == "smiledental.com"
    assert row["deal_value"] == 5000.0
