"""Slack delivery — Block Kit digest + one card per signal via the existing
webhook. Degrades to formatted text dicts when no webhook is configured, so
the pipeline always completes (house doctrine)."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

_TIER_BADGE = {"verified": "✅ VERIFIED", "probable": "⚠️ PROBABLE"}
_SEV_EMOJI = {"high": "🔴", "medium": "🟠", "low": "🟢"}
_DRAFT_CAP = 650  # keep cards scannable; the full draft is one click away in the UI
_FOOTER = "🕴️ SDR Agent · agent47.tech"


def _post(payload: dict, url: str) -> bool:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return 200 <= resp.status < 300
    except (urllib.error.URLError, OSError):
        return False


def digest_blocks(batch: dict) -> list[dict]:
    """The batch summary that opens every scan post."""
    line = (f"*{batch.get('total', 0)}* leads scanned · "
            f"*{batch.get('resolved', 0)}* resolved · "
            f"*{batch.get('signals_found', 0)}* signals · "
            f"{batch.get('errors', 0)} errors")
    if batch.get("verified") or batch.get("probable"):
        line += (f"\n✅ {batch.get('verified', 0)} verified · "
                 f"⚠️ {batch.get('probable', 0)} probable — ranked cards below 👇")
    blocks = [
        {"type": "header",
         "text": {"type": "plain_text", "text": f"🕴️ SDR Scan #{batch.get('batch_id', '?')}"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": line}},
    ]
    if batch.get("unresolved"):
        blocks.append({"type": "context", "elements": [{
            "type": "mrkdwn",
            "text": f"🔍 {batch['unresolved']} lead(s) unresolved — check their domains; "
                    f"they were not pitched."}]})
    return blocks


def signal_card_blocks(lead: dict, signal: dict, draft: str) -> list[dict]:
    """One opportunity card: who, what, proof, offer, draft."""
    badge = _TIER_BADGE.get(signal.get("tier", ""), signal.get("tier", ""))
    sev = (signal.get("severity") or "low").upper()
    contact = " · ".join(x for x in (lead.get("contact_name", ""),
                                     lead.get("contact_email", "")) if x)
    fields = [
        {"type": "mrkdwn", "text": f"*Signal:*\n{signal.get('summary', '')}"},
        {"type": "mrkdwn", "text": f"*Matched offer:*\n💰 {signal.get('matched_offer', '')}"},
    ]
    if signal.get("evidence_url"):
        fields.append({"type": "mrkdwn",
                       "text": f"*Evidence:*\n🔗 <{signal['evidence_url']}|source>"})
    if contact:
        fields.append({"type": "mrkdwn", "text": f"*Contact:*\n👤 {contact}"})
    sev_dot = _SEV_EMOJI.get((signal.get("severity") or "low").lower(), "🟢")
    draft_text = (draft or "").strip()
    if len(draft_text) > _DRAFT_CAP:
        draft_text = draft_text[:_DRAFT_CAP].rstrip() + " …"
    return [
        {"type": "header", "text": {"type": "plain_text",
                                    "text": f"🚀 {lead.get('name', 'Unknown')}"}},
        {"type": "context", "elements": [{
            "type": "mrkdwn",
            "text": f"{badge} · {sev_dot} {sev} · {signal.get('signal_type', '')} · "
                    f"score {signal.get('score', 0):.1f}"}]},
        {"type": "section", "fields": fields},
        {"type": "section", "text": {"type": "mrkdwn",
                                     "text": f"*✉️ Suggested outreach:*\n>{draft_text}"}},
        {"type": "context", "elements": [{"type": "mrkdwn", "text": _FOOTER}]},
        {"type": "divider"},
    ]


def deliver_results(digest: list[dict], cards: list[list[dict]]) -> dict:
    """Post digest then each card. mode: webhook | formatted (no webhook set)."""
    webhook = os.getenv("SLACK_WEBHOOK_URL")
    if not webhook:
        return {"mode": "formatted", "delivered": 0,
                "blocks": {"digest": digest, "cards": cards},
                "note": "SLACK_WEBHOOK_URL not set; returning Block Kit payloads."}
    sent = 1 if _post({"blocks": digest}, webhook) else 0
    for card in cards:
        sent += 1 if _post({"blocks": card}, webhook) else 0
    return {"mode": "webhook" if sent else "formatted", "delivered": sent}
