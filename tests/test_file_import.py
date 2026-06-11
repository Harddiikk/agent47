"""Tests for sdr/file_import.py — Excel/CSV attachments become imported leads."""
import io

import openpyxl

from sdr.file_import import csv_text_from_xlsx, try_import_blob
from sdr.ingest import load_leads

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _xlsx_bytes(rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


CRM_ROWS = [
    ["First name", "Last name", "Company", "Website", "Email", "City"],
    ["Raj", "Patel", "Smile Dental", "smiledental.com", "raj@smile.com", "Austin"],
    ["Mia", "Lopez", "GlowSpa", "glowspa.com", "mia@glowspa.com", "Miami"],
]


def test_csv_text_from_xlsx_roundtrip():
    text = csv_text_from_xlsx(_xlsx_bytes(CRM_ROWS))
    assert text.splitlines()[0].startswith("First name,Last name,Company")
    assert "smiledental.com" in text


def test_try_import_blob_xlsx_end_to_end(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    out = try_import_blob(_xlsx_bytes(CRM_ROWS), XLSX_MIME, "leads.xlsx")
    assert out["ok"] is True and out["imported"] == 2
    rows = load_leads("data/leads.csv")
    assert rows[0]["name"] == "Smile Dental"          # smart header mapping ran
    assert rows[0]["contact_name"] == "Raj Patel"


def test_try_import_blob_idempotent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    data = _xlsx_bytes(CRM_ROWS)
    first = try_import_blob(data, XLSX_MIME, "leads.xlsx")
    again = try_import_blob(data, XLSX_MIME, "leads.xlsx")   # history replay
    assert first.get("already_imported") is None
    assert again["already_imported"] is True
    assert len(load_leads("data/leads.csv")) == 2            # not duplicated


def test_try_import_blob_csv_mime(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    csv_bytes = b"Company,Website\nAcme Clinic,acme.com\n"
    out = try_import_blob(csv_bytes, "text/csv", "list.csv")
    assert out["ok"] is True and out["imported"] == 1


def test_try_import_blob_non_spreadsheet_returns_none():
    assert try_import_blob(b"x", "image/png", "pic.png") is None


def test_try_import_blob_garbage_reports_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    out = try_import_blob(b"not a real file at all", XLSX_MIME, "bad.xlsx")
    assert out["ok"] is False
    assert out["error"]


def test_reupload_same_rows_different_file_reports_not_failure(tmp_path, monkeypatch):
    """Regression: a CSV re-upload of already-imported leads reported
    '0 leads imported' and the model treated it as a format failure."""
    monkeypatch.chdir(tmp_path)
    xlsx = _xlsx_bytes(CRM_ROWS)
    first = try_import_blob(xlsx, XLSX_MIME, "leads.xlsx")
    assert first["imported"] == 2
    # same rows, different bytes/format -> different hash, not 'already_imported'
    csv_bytes = ("First name,Last name,Company,Website,Email,City\n"
                 "Raj,Patel,Smile Dental,smiledental.com,raj@smile.com,Austin\n"
                 "Mia,Lopez,GlowSpa,glowspa.com,mia@glowspa.com,Miami\n").encode()
    again = try_import_blob(csv_bytes, "text/csv", "leads.csv")
    assert again["ok"] is True
    assert again["imported"] == 0
    assert again["total_in_file"] == 2
    assert again["duplicates_skipped"] == 2

    from shared.attachment_guard import _import_note
    note = _import_note("leads.csv", again)
    assert "NOT a failure" in note
    assert "get_all_signals" in note          # show existing signals, no pointless rescan
    assert "re-paste" in note or "re-upload" in note


def test_import_note_targets_new_leads_only(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    try_import_blob(_xlsx_bytes(CRM_ROWS), XLSX_MIME, "first.xlsx")
    # second file adds ONE new lead alongside one duplicate
    new_rows = [CRM_ROWS[0],
                CRM_ROWS[1],
                ["Zoe", "Park", "FreshClinic", "freshclinic.com", "z@fresh.com", "Denver"]]
    out = try_import_blob(_xlsx_bytes(new_rows), XLSX_MIME, "second.xlsx")
    assert out["imported"] == 1
    assert out["imported_names"] == ["FreshClinic"]
    from shared.attachment_guard import _import_note
    note = _import_note("second.xlsx", out)
    assert 'names="FreshClinic"' in note
    assert "ONLY the new leads" in note
