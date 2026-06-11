"""Telegram delivery — scan results on the founder's phone, zero infrastructure.

Activates when TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are set (a 2-minute
@BotFather setup); otherwise every call quietly no-ops. Same doctrine as the
Slack path: never raises, always reports what it did.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

_API = "https://api.telegram.org/bot{token}/sendMessage"


def _send(text: str, token: str, chat_id: str) -> bool:
    payload = json.dumps({"chat_id": chat_id, "text": text,
                          "disable_web_page_preview": True}).encode("utf-8")
    req = urllib.request.Request(_API.format(token=token), data=payload,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return 200 <= resp.status < 300
    except (urllib.error.URLError, OSError):
        return False


def telegram_configured() -> bool:
    return bool(os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"))


def format_digest_text(summary: dict, top: list[dict], limit: int = 3) -> str:
    """Plain-text digest for a phone screen: counts + the top signals."""
    lines = [
        f"🕴️ SDR Agent — scan #{summary.get('batch_id', '?')} done",
        f"{summary.get('total', 0)} leads · {summary.get('signals_found', 0)} signals "
        f"(✅{summary.get('verified', 0)} / ⚠️{summary.get('probable', 0)}) · "
        f"{summary.get('unresolved', 0)} unresolved",
    ]
    for i, t in enumerate(top[:limit], 1):
        lines.append("")
        lines.append(f"{i}. {t.get('name', '?')} [{(t.get('severity') or '').upper()}]")
        lines.append(f"   {t.get('summary', '')[:200]}")
        lines.append(f"   💰 {t.get('offer', '')}")
        if t.get("evidence_url"):
            lines.append(f"   🔗 {t['evidence_url']}")
    if not top:
        lines.append("No new signals this run.")
    return "\n".join(lines)


def deliver_digest_telegram(summary: dict, top: list[dict]) -> dict:
    """Send the scan digest to the founder's Telegram. mode: telegram | skipped."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return {"mode": "skipped", "reason": "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set"}
    ok = _send(format_digest_text(summary, top), token, chat_id)
    return {"mode": "telegram" if ok else "failed", "delivered": 1 if ok else 0}
