"""Tests for shared/outreach.py — offline; no real API or network."""
import pytest

from shared.outreach import (
    deliver_to_slack,
    draft_outreach,
    format_slack_message,
    scan_and_deliver,
)


class _Resp:
    def __init__(self, text):
        self.text = text


class _Models:
    def __init__(self, text=None, exc=None):
        self._text = text
        self._exc = exc

    def generate_content(self, *, model, contents):
        if self._exc:
            raise self._exc
        return _Resp(self._text)


class _Client:
    def __init__(self, text=None, exc=None):
        self.models = _Models(text=text, exc=exc)


def _noop(_):
    pass


CUSTOMER = {"name": "Milan Laser", "contact_email": "info@milan.com"}
SIGNAL = {
    "summary": "opened 30 new clinics this year",
    "severity": "high",
    "signal_type": "expansion",
    "confidence": 0.9,
    "evidence": [{"claim": "30 clinics", "source_url": "https://news.com/milan"}],
}


def test_draft_outreach_success_uses_model_text():
    out = draft_outreach(CUSTOMER, SIGNAL, client=_Client(text="Hello Milan, congrats!"),
                         sleep=_noop)
    assert out == "Hello Milan, congrats!"


def test_draft_outreach_falls_back_on_error():
    out = draft_outreach(CUSTOMER, SIGNAL, client=_Client(exc=ValueError("400 bad")),
                         sleep=_noop)
    assert "Milan Laser" in out  # template fallback references the business
    assert len(out) > 0


def test_format_slack_message_has_all_parts():
    msg = format_slack_message(CUSTOMER, SIGNAL, "Drafted email body")
    assert "Milan Laser" in msg
    assert "opened 30 new clinics" in msg
    assert "https://news.com/milan" in msg
    assert "Drafted email body" in msg
    assert "Action" in msg


def test_deliver_to_slack_formatted_fallback(monkeypatch):
    for k in ("COMPOSIO_API_KEY", "COMPOSIO_USER_ID", "SLACK_WEBHOOK_URL"):
        monkeypatch.delenv(k, raising=False)
    out = deliver_to_slack(["msg one", "msg two"])
    assert out["mode"] == "formatted"
    assert out["delivered"] == 2
    assert out["blocks"] == ["msg one", "msg two"]


def test_scan_and_deliver_pipeline(monkeypatch):
    for k in ("COMPOSIO_API_KEY", "COMPOSIO_USER_ID", "SLACK_WEBHOOK_URL"):
        monkeypatch.delenv(k, raising=False)

    fake_scan = lambda csv_path, *, db_path=None: {  # noqa: E731
        "scanned": 3,
        "signals_found": 1,
        "ranked": [{**CUSTOMER, **SIGNAL}],
        "errors": [],
    }
    fake_draft = lambda customer, signal: "Drafted for " + customer["name"]  # noqa: E731

    out = scan_and_deliver(scan_fn=fake_scan, draft_fn=fake_draft)
    assert out["scanned"] == 3
    assert out["signals_found"] == 1
    assert out["drafted"] == 1
    assert out["delivery"]["mode"] == "formatted"
    assert out["top"][0]["name"] == "Milan Laser"
    assert out["top"][0]["draft"] == "Drafted for Milan Laser"


def test_scan_and_deliver_no_signals(monkeypatch):
    fake_scan = lambda csv_path, *, db_path=None: {  # noqa: E731
        "scanned": 2, "signals_found": 0, "ranked": [], "errors": [],
    }
    out = scan_and_deliver(scan_fn=fake_scan)
    assert out["drafted"] == 0
    assert out["delivery"]["mode"] == "skipped"
