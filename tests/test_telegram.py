"""Tests for sdr/telegram.py — phone delivery, env-activated."""
import sdr.telegram as tg

SUMMARY = {"batch_id": 7, "total": 8, "signals_found": 2, "verified": 1,
           "probable": 1, "unresolved": 3}
TOP = [{"name": "Acme Dental", "severity": "high",
        "summary": "opened a second clinic in Frisco",
        "offer": "Local SEO", "evidence_url": "https://news.com/a"}]


def test_format_digest_text():
    text = tg.format_digest_text(SUMMARY, TOP)
    for needle in ("scan #7", "8 leads", "Acme Dental", "[HIGH]", "Local SEO",
                   "news.com"):
        assert needle in text, f"missing {needle}"


def test_format_digest_no_signals():
    assert "No new signals" in tg.format_digest_text(SUMMARY, [])


def test_deliver_skipped_without_env(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    out = tg.deliver_digest_telegram(SUMMARY, TOP)
    assert out["mode"] == "skipped"


def test_deliver_sends_when_configured(monkeypatch):
    sent = []
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t0k")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
    monkeypatch.setattr(tg, "_send", lambda text, token, chat: sent.append(
        (text, token, chat)) or True)
    out = tg.deliver_digest_telegram(SUMMARY, TOP)
    assert out["mode"] == "telegram" and out["delivered"] == 1
    assert sent[0][1] == "t0k" and "Acme Dental" in sent[0][0]
