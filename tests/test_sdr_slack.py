"""Tests for sdr/slack.py — Block Kit payloads + delivery fallback."""
import json

from sdr.slack import deliver_results, digest_blocks, signal_card_blocks

LEAD = {"name": "Acme Dental", "contact_name": "Dr. A", "contact_email": "a@acme.com"}
SIGNAL = {"signal_type": "expansion", "summary": "opened a new Frisco clinic",
          "tier": "verified", "severity": "high", "matched_offer": "Local SEO",
          "score": 7.5, "evidence_url": "https://news.com/a"}


def test_digest_blocks_shape():
    blocks = digest_blocks({"batch_id": 3, "total": 10, "resolved": 8,
                            "signals_found": 2, "errors": 1, "unresolved": 2})
    assert blocks[0]["type"] == "header"
    flat = json.dumps(blocks)
    assert "10" in flat and "unresolved" in flat


def test_signal_card_has_all_parts():
    blocks = signal_card_blocks(LEAD, SIGNAL, "Hi Acme, congrats…")
    flat = json.dumps(blocks)
    for needle in ("Acme Dental", "VERIFIED", "HIGH", "Frisco", "Local SEO",
                   "news.com", "congrats", "a@acme.com"):
        assert needle in flat, f"missing {needle}"


def test_deliver_results_formatted_fallback(monkeypatch):
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    out = deliver_results(digest_blocks({"batch_id": 1, "total": 1, "resolved": 1,
                                         "signals_found": 0, "errors": 0,
                                         "unresolved": 0}), [])
    assert out["mode"] == "formatted"


def test_deliver_results_posts_each_card(monkeypatch):
    posted = []
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.test/x")
    import sdr.slack as mod
    monkeypatch.setattr(mod, "_post", lambda payload, url: posted.append(payload) or True)
    cards = [signal_card_blocks(LEAD, SIGNAL, "draft")]
    out = deliver_results(digest_blocks({"batch_id": 1, "total": 1, "resolved": 1,
                                         "signals_found": 1, "errors": 0,
                                         "unresolved": 0}), cards)
    assert out["mode"] == "webhook"
    assert len(posted) == 2  # digest + one card
