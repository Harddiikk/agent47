"""Outreach drafting + Slack delivery + the end-to-end book-scan pipeline.

- draft_outreach : a short personalized email referencing the specific real signal.
- deliver_to_slack: posts via Composio (existing path) → Slack Incoming Webhook →
                    formatted text blocks. Always completes; reports which mode ran.
- scan_and_deliver: the full pipeline both the ADK tool and the CLI script call.
"""
from __future__ import annotations

import json
import os
import time
from typing import Callable, Optional

from shared.config import DEFAULT_MODEL

_TRANSIENT = ("503", "unavailable", "resource_exhausted", "overloaded", "high demand", "429")

_DRAFT_PROMPT = """Write a short, warm B2B outreach email (90-130 words) from an AI automation \
agency to a PAST customer, congratulating them on a specific growth milestone and offering to help \
them scale operations with AI automation.

Customer: {name}
Growth signal: {summary}
Reference this concretely. Be specific, not generic. No subject line. NEVER use bracketed \
placeholders like [Name] or [Your Agency Name]; use the real business name. Sign off with \
"The Agent 47 team" on its own line. Plain text. Never use em dashes or double hyphens. \
Write like a busy founder typing a quick note, not like marketing copy. \
End with a soft call to action to reconnect."""


def _is_transient(err: str) -> bool:
    e = err.lower()
    return any(t in e for t in _TRANSIENT)


def _fallback_draft(customer: dict, signal: dict) -> str:
    name = customer.get("name", "there")
    summary = signal.get("summary", "your recent growth")
    return (
        f"Hi {name} team,\n\n"
        f"Congratulations on {summary} — exciting momentum. When we worked together we helped "
        f"teams like yours automate the operational load that comes with growth (intake, "
        f"scheduling, follow-ups). As you scale, we'd love to reconnect and see where AI "
        f"automation could save your team hours each week.\n\n"
        f"Open to a quick 15-minute call next week?\n\n— The Agent 47 team"
    )


def draft_outreach(
    customer: dict,
    signal: dict,
    *,
    client=None,
    model: str = DEFAULT_MODEL,
    max_retries: int = 2,
    backoff: float = 2.0,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    """Draft a personalized outreach email. Never raises — falls back to a template."""
    prompt = _DRAFT_PROMPT.format(
        name=customer.get("name", ""), summary=signal.get("summary", "")
    )
    for attempt in range(max_retries + 1):
        try:
            from google import genai

            cli = client or genai.Client()
            resp = cli.models.generate_content(model=model, contents=prompt)
            text = (getattr(resp, "text", None) or "").strip()
            if text:
                return text
        except Exception as e:  # noqa: BLE001
            if not _is_transient(f"{e}"):
                break
        if attempt < max_retries:
            sleep(backoff * (2**attempt))
    return _fallback_draft(customer, signal)


def format_slack_message(customer: dict, signal: dict, draft: str) -> str:
    """One Slack message: customer + signal + top evidence link + draft + CTA."""
    name = customer.get("name", "Unknown")
    sev = signal.get("severity", "low").upper()
    stype = signal.get("signal_type", "neutral")
    summary = signal.get("summary", "")
    evidence = signal.get("evidence") or []
    top_link = ""
    for ev in evidence:
        if str(ev.get("source_url", "")).startswith("http"):
            top_link = ev["source_url"]
            break
    conf = signal.get("confidence", 0.0)

    lines = [f"*🚀 {name}* — {stype} signal [{sev}]  ·  confidence {conf:.0%}"]
    if summary:
        lines.append(f"> {summary}")
    if top_link:
        lines.append(f"🔗 Evidence: {top_link}")
    lines += ["", "*Suggested outreach:*", draft, ""]
    email = customer.get("contact_email", "")
    lines.append(f"👉 *Action:* reconnect with {name}" + (f" ({email})" if email else ""))
    return "\n".join(lines).strip()


def _deliver_via_webhook(text: str, webhook_url: str) -> bool:
    """Post to a Slack Incoming Webhook using stdlib only. Returns True on 2xx."""
    import urllib.error
    import urllib.request

    data = json.dumps({"text": text}).encode("utf-8")
    req = urllib.request.Request(
        webhook_url, data=data, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return 200 <= resp.status < 300
    except (urllib.error.URLError, OSError):
        return False


def _deliver_via_composio(text: str, channel: str) -> bool:
    """Best-effort post via the existing Composio path. Any failure -> False."""
    api_key = os.getenv("COMPOSIO_API_KEY")
    user_id = os.getenv("COMPOSIO_USER_ID")
    if not api_key or not user_id:
        return False
    try:
        from composio import Composio

        client = Composio(api_key=api_key)
        # Slack "send message" toolkit slug; arguments kept generic across versions.
        client.tools.execute(
            "SLACK_SENDS_A_MESSAGE_TO_A_SLACK_CHANNEL",
            user_id=user_id,
            arguments={"channel": channel, "text": text},
        )
        return True
    except Exception:  # noqa: BLE001 — graceful: caller falls through to other modes
        return False


def deliver_to_slack(message_blocks: list[str], *, channel: Optional[str] = None) -> dict:
    """Deliver messages to Slack. Tries webhook → Composio → formatted text.

    The webhook (when set) is preferred: it's deterministic and posts each signal
    as its own message, which reads far better in-channel than one giant block.
    Always completes. `mode` reports what actually ran: webhook | composio | formatted.
    """
    channel = channel or os.getenv("SLACK_CHANNEL", "#general")
    webhook = os.getenv("SLACK_WEBHOOK_URL")

    if webhook and message_blocks:
        sent = sum(1 for b in message_blocks if _deliver_via_webhook(b, webhook))
        if sent:
            return {"mode": "webhook", "delivered": sent, "channel": channel}

    if os.getenv("COMPOSIO_API_KEY") and os.getenv("COMPOSIO_USER_ID"):
        if all(_deliver_via_composio(b, channel) for b in message_blocks) and message_blocks:
            return {"mode": "composio", "delivered": len(message_blocks), "channel": channel}

    # Guaranteed demo path: return the formatted blocks so the pipeline always completes.
    return {
        "mode": "formatted",
        "delivered": len(message_blocks),
        "channel": channel,
        "blocks": message_blocks,
        "note": "Composio/Slack webhook not configured; returning formatted Slack blocks.",
    }


def scan_and_deliver(
    csv_path: Optional[str] = None,
    *,
    db_path: Optional[str] = None,
    deliver: bool = True,
    draft_fn: Callable[..., str] = draft_outreach,
    scan_fn: Callable[..., dict] = None,  # injectable for tests
    max_signals: int = 10,
) -> dict:
    """Full pipeline: scan the book → draft outreach per signal → deliver to Slack.

    Returns: {scanned, signals_found, drafted, delivery, top: [...] }
    """
    from shared.book import DEFAULT_CSV, DEFAULT_DB, scan_book

    _scan = scan_fn or scan_book
    result = _scan(csv_path or DEFAULT_CSV, db_path=db_path or DEFAULT_DB)
    ranked = result.get("ranked", [])[:max_signals]

    messages: list[str] = []
    top: list[dict] = []
    for row in ranked:
        draft = draft_fn(row, row)
        messages.append(format_slack_message(row, row, draft))
        top.append(
            {
                "name": row.get("name"),
                "signal_type": row.get("signal_type"),
                "severity": row.get("severity"),
                "confidence": row.get("confidence"),
                "summary": row.get("summary"),
                "evidence": row.get("evidence", [])[:1],
                "draft": draft,
            }
        )

    delivery = deliver_to_slack(messages) if (deliver and messages) else {
        "mode": "skipped", "delivered": 0
    }

    return {
        "scanned": result.get("scanned", 0),
        "signals_found": result.get("signals_found", 0),
        "drafted": len(messages),
        "delivery": delivery,
        "top": top,
        "errors": result.get("errors", []),
    }
