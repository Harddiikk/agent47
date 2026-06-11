"""Intelligence — sub-agent for signal monitoring and recommendations.

Reads the REAL SDR scan ledger (data/sdr.db) — the verified signals the
Research agent found — not demo data. The weekly brief is about the founder's
actual book.
"""

import os
from pathlib import Path

from google.adk import Agent
from shared.attachment_guard import strip_unsupported_attachments
from shared.config import DEFAULT_MODEL

PROMPT_PATH = Path(__file__).parent.parent.parent / "shared" / "prompts" / "intelligence_system.md"
SYSTEM_PROMPT = PROMPT_PATH.read_text()

_VALID_SEVERITY = ("low", "medium", "high")
_VALID_TYPES = ("expansion", "risk", "health", "neutral", "update")


def _store():
    from sdr.store import SdrStore

    return SdrStore(os.getenv("SDR_DB_PATH", "data/sdr.db"))


def _signal_rows() -> list[dict]:
    """Join signals with lead names into flat, JSON-serializable rows."""
    store = _store()
    rows = []
    for s in store.list_signals():
        lead = store.get_lead(s["lead_id"]) or {}
        rows.append({
            "client": lead.get("name", f"lead#{s['lead_id']}"),
            "type": s["signal_type"],
            "severity": s["severity"],
            "tier": s["tier"],
            "summary": s["summary"],
            "matched_offer": s["matched_offer"],
            "score": s["score"],
            "state": s["state"],
            "found_at": s["created_at"],
        })
    return rows


def get_all_signals() -> dict:
    """Return every signal the SDR scans have found, ranked by score.

    Use this to build the weekly Intelligence Brief over the founder's real
    book. Each row carries the business name, type, severity, verification
    tier, matched offer, and when it was found.
    """
    return {"signals": _signal_rows()}


def get_signals_for_client(client: str) -> dict:
    """Return all scan signals for one business (case-insensitive name match).

    Args:
        client: The business name or a distinctive part of it, e.g. 'SkinSpirit'.
    """
    needle = (client or "").strip().lower()
    found = [r for r in _signal_rows() if needle and needle in r["client"].lower()]
    return {"client": client, "signals": found}


def get_signals_by_severity(severity: str) -> dict:
    """Return all scan signals at a given severity level.

    Args:
        severity: One of 'low', 'medium', or 'high'.
    """
    if severity not in _VALID_SEVERITY:
        return {"error": f"invalid severity '{severity}'; expected low, medium, or high"}
    return {"severity": severity,
            "signals": [r for r in _signal_rows() if r["severity"] == severity]}


def get_signals_by_type(signal_type: str) -> dict:
    """Return all scan signals of a given type.

    Args:
        signal_type: One of 'expansion', 'risk', 'health', 'neutral', or
            'update' (website-change signals).
    """
    if signal_type not in _VALID_TYPES:
        return {"error": f"invalid type '{signal_type}'; expected one of {', '.join(_VALID_TYPES)}"}
    return {"type": signal_type,
            "signals": [r for r in _signal_rows() if r["type"] == signal_type]}


INTELLIGENCE_TOOLS = [
    get_all_signals,
    get_signals_for_client,
    get_signals_by_severity,
    get_signals_by_type,
]

intelligence = Agent(
    name="intelligence",
    model=DEFAULT_MODEL,
    instruction=SYSTEM_PROMPT,
    tools=INTELLIGENCE_TOOLS,
    before_model_callback=strip_unsupported_attachments,
)

root_agent = intelligence
