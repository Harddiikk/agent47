"""Tests for shared/attachment_guard.py — unsupported blobs stripped pre-model."""
from google.genai import types

from shared.attachment_guard import strip_unsupported_attachments

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class _Req:
    def __init__(self, contents):
        self.contents = contents


def _content(*parts):
    return types.Content(role="user", parts=list(parts))


def _xlsx_bytes(rows):
    import io

    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_xlsx_blob_is_imported_as_leads(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    data = _xlsx_bytes([["Company", "Website"], ["Acme Dental", "acme.com"]])
    req = _Req([_content(
        types.Part(text="here is my customer file"),
        types.Part(inline_data=types.Blob(mime_type=XLSX, data=data,
                                          display_name="leads.xlsx")),
    )])
    assert strip_unsupported_attachments(None, req) is None  # continue request
    parts = req.contents[0].parts
    assert parts[1].inline_data is None              # blob gone
    assert "leads.xlsx" in parts[1].text
    assert "1 leads imported" in parts[1].text       # actually imported
    assert parts[0].text == "here is my customer file"  # untouched
    from sdr.ingest import load_leads
    assert load_leads("data/leads.csv")[0]["name"] == "Acme Dental"


def test_corrupt_xlsx_reports_error_not_crash(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    req = _Req([_content(
        types.Part(inline_data=types.Blob(mime_type=XLSX, data=b"PK",
                                          display_name="bad.xlsx")),
    )])
    strip_unsupported_attachments(None, req)
    txt = req.contents[0].parts[0].text
    assert "could not be imported" in txt
    assert "bad.xlsx" in txt


def test_supported_attachments_kept():
    img = types.Part(inline_data=types.Blob(mime_type="image/png", data=b"x"))
    pdf = types.Part(inline_data=types.Blob(mime_type="application/pdf", data=b"x"))
    req = _Req([_content(img, pdf)])
    strip_unsupported_attachments(None, req)
    assert req.contents[0].parts[0].inline_data is not None
    assert req.contents[0].parts[1].inline_data is not None


def test_history_blobs_also_stripped(tmp_path, monkeypatch):
    # Poisoned-session case: blob deep in history, not the latest turn.
    monkeypatch.chdir(tmp_path)
    req = _Req([
        _content(types.Part(inline_data=types.Blob(mime_type=XLSX, data=b"PK"))),
        _content(types.Part(text="retry")),
        _content(types.Part(text="hey")),
    ])
    strip_unsupported_attachments(None, req)
    assert req.contents[0].parts[0].inline_data is None


def test_tolerates_empty_and_none():
    assert strip_unsupported_attachments(None, None) is None
    assert strip_unsupported_attachments(None, _Req([])) is None


def test_all_agents_have_guard():
    from agents.account_manager import account_manager, make_client_agent
    from agents.sdr_agent import agent47
    from agents.execution import execution
    from agents.intelligence import intelligence
    from agents.onboarding import onboarding
    for a in (agent47, onboarding, account_manager, intelligence, execution,
              make_client_agent("X", "ctx")):
        cb = a.before_model_callback
        cbs = cb if isinstance(cb, list) else [cb]
        assert any(getattr(c, "__name__", "") == "strip_unsupported_attachments"
                   for c in cbs), f"{a.name} missing guard"
