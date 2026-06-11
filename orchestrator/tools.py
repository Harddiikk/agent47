"""Manager tools exposed to Agent 47.

Thin, JSON-returning wrappers over a module-level Dispatcher so ADK can call
them. The dispatcher (and its DB path / workspace root) come from env so a
deployed daemon and the local chat share the same state.
"""
from __future__ import annotations

import os
from typing import Optional

from orchestrator.dispatcher import Dispatcher
from orchestrator.store import Store

_DB_PATH = os.getenv("MOU_DB_PATH", "orchestrator/state.db")
_WORKSPACES = os.getenv("MOU_WORKSPACES", "workspaces")

# Default dispatcher used by the ADK tools. Tests construct their own Dispatcher.
dispatcher = Dispatcher(Store(_DB_PATH), workspaces_root=_WORKSPACES)


def add_client(name: str, context: str = "") -> dict:
    """Register a new client, or add more context to an existing one.

    Use this whenever the founder introduces a client or shares details about
    them (industry, scope, contacts, current state). Context accumulates.

    Args:
        name: Short client identifier, e.g. 'acme'.
        context: Free-form details about the client and the work.
    """
    return dispatcher.add_client(name, context)


def list_clients() -> dict:
    """List every known client and their accumulated context."""
    return dispatcher.list_clients()


def dispatch_plan(client_name: str, task: str) -> dict:
    """Plan a piece of work for a client by dispatching a read-only Gemini worker.

    The worker analyzes the client's context plus the task and returns a detailed
    implementation plan and architecture WITHOUT building anything yet. The plan
    is saved with a session id so it can be approved and then built. Returns the
    plan text and a plan_id. This may take some time while the worker thinks.

    Args:
        client_name: The client this work is for (must already exist).
        task: What the founder wants planned, in plain language.
    """
    return dispatcher.dispatch_plan(client_name, task)


def list_plans(status: Optional[str] = None) -> dict:
    """List dispatched plans, optionally filtered by status.

    Args:
        status: Optional filter — one of 'planned', 'approved', 'building',
            'done', 'failed', 'rejected'.
    """
    return dispatcher.list_plans(status)


def get_plan(plan_id: str) -> dict:
    """Fetch the full record (including plan text) for a single plan.

    Args:
        plan_id: The id returned by dispatch_plan.
    """
    return dispatcher.get_plan(plan_id)


def scan_my_book() -> dict:
    """Scan the founder's PAST customers for growth/expansion signals and act on them.

    Researches every customer in data/customers.csv live on the web (Google Search
    grounding), keeps only real recent signals (new locations, hires, funding,
    press), ranks them, drafts a personalized outreach for each, and posts them to
    Slack. Use this when the founder says "scan my book", "find expansion signals",
    or "who should I reach out to". This runs live web research and may take a bit.

    Returns a concise summary: how many were scanned, how many signals were found,
    where they were delivered, and the top 3 opportunities.
    """
    from shared.outreach import scan_and_deliver

    result = scan_and_deliver()
    return {
        "scanned": result.get("scanned", 0),
        "signals_found": result.get("signals_found", 0),
        "delivery_mode": result.get("delivery", {}).get("mode"),
        "top_3": result.get("top", [])[:3],
    }


def scan_leads(csv_path: str = "data/leads.csv", names: str = "") -> dict:
    """Run the SDR pipeline: verify identity, research live, detect what
    changed, match each signal to a service offer, and post ranked cards to
    Slack. Use when the founder says "scan my leads", "run the SDR scan", or a
    lead file was just imported. May take a few minutes.

    Scope: when an import note lists newly added leads, pass them via `names`
    so ONLY those are researched (faster, cheaper, no re-crawling the book).
    Same when the founder names specific leads ("scan Acme and GlowSpa").
    For a full-book scan ("scan my leads", first scan) leave names empty.
    Never build csv_path from an uploaded filename.

    Args:
        csv_path: Leave at the default lead book.
        names: Optional comma-separated lead names to scan only those
            (case-insensitive, partial names fine).
    """
    from pathlib import Path

    from sdr.pipeline import run_scan

    default = "data/leads.csv"
    path = csv_path or default
    if not Path(path).exists():
        if Path(default).exists():
            path = default  # an invented/guessed path falls back to the book
        else:
            return {"ok": False,
                    "error": "no lead book yet. Ask the founder to drop their "
                             "Excel/CSV file in the chat or paste leads as "
                             "text, then scan."}
    only = [n for n in (names or "").split(",") if n.strip()] or None
    result = run_scan(path, only_names=only)
    out = {
        "batch_id": result["batch_id"],
        "total": result["total"],
        "resolved": result["resolved"],
        "unresolved": result["unresolved"],
        "signals_found": result["signals_found"],
        "already_tracked": result.get("already_tracked", 0),
        "delivery_mode": result["delivery"].get("mode"),
        "top_3": result["top"][:3],
    }
    if out["signals_found"] == 0 and out["already_tracked"] > 0:
        out["note"] = (
            "0 NEW signals is normal on a rescan: every previously found signal "
            "is still on file (the system never reposts duplicates). Tell the "
            "founder this clearly, then use get_all_signals to show the "
            f"{out['already_tracked']} active signal(s) they can act on.")
    return out


def import_leads(csv_text: str, replace: bool = False,
                 column_map: Optional[dict] = None) -> dict:
    """Save leads the founder pastes into the chat as CSV text, so scan_leads
    can research them. Use when the founder pastes a lead list or asks to
    import/add leads. Paste the founder's CSV AS-IS — headers are normalized
    automatically (Company→name, Website→domain, First/Last name→contact_name,
    Email→contact_email, City→location, etc.). Only if the import reports it
    could not find usable columns, look at the founder's headers yourself and
    retry with column_map={'their header': 'canonical field'} — canonical
    fields: name (the BUSINESS), domain, linkedin_url, location, services,
    contact_name, contact_email, last_service, deal_value, status. File
    uploads (xlsx etc.) are NOT supported — ask for pasted CSV text instead.

    Args:
        csv_text: CSV content, header row first, exactly as the founder pasted.
        replace: True to replace the existing lead book instead of appending.
        column_map: Optional explicit header mapping for unusual headers.
    """
    from sdr.ingest import save_leads_text

    try:
        result = save_leads_text(csv_text, "data/leads.csv", replace=replace,
                                 column_map=column_map)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, **result,
            "next_step": "run scan_leads() to research the imported leads"}


def set_offers(offers: list) -> dict:
    """Configure what THIS founder sells, so signals match THEIR services.

    Use whenever a founder/tester describes their products or services (e.g.
    "we sell web design and a booking app"). Derive trigger keywords yourself:
    words likely to appear in a growth signal that make the offer relevant
    (e.g. booking app → ["booking", "appointment", "front desk", "hiring"]).
    Replaces the whole catalog — include every offer they mention.

    Args:
        offers: List of {"name": "<service name>", "triggers": ["kw", ...]}.
    """
    import json as _json
    from pathlib import Path as _Path

    cleaned = []
    for o in offers or []:
        if not isinstance(o, dict) or not str(o.get("name", "")).strip():
            continue
        triggers = [str(t).strip().lower() for t in (o.get("triggers") or [])
                    if str(t).strip()]
        cleaned.append({"name": str(o["name"]).strip(), "triggers": triggers})
    if not cleaned:
        return {"ok": False,
                "error": "no valid offers; each needs at least a 'name'"}
    path = _Path("data/offers.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json.dumps(cleaned, indent=2))
    return {"ok": True, "offers_saved": [o["name"] for o in cleaned],
            "note": "future scans will match signals against these offers"}


def list_offers() -> dict:
    """Show the current offer catalog (what the founder sells) used for
    signal-to-offer matching."""
    from sdr.offers import load_offers

    return {"offers": load_offers()}


# Full registry of manager tools (kept for tests/back-compat and ad-hoc use).
MANAGER_TOOLS = [
    add_client,
    list_clients,
    dispatch_plan,
    list_plans,
    get_plan,
    scan_my_book,
    scan_leads,
    import_leads,
    set_offers,
    list_offers,
]

# Role separation: each agent gets only its lane.
#   coordinator (root)  -> work dispatch only; everything else is routed
#   research            -> the scan pipelines
#   onboarding          -> offers + lead import (defined in its module)
#   account_manager     -> client records (defined in its module)
COORDINATOR_TOOLS = [dispatch_plan, list_plans, get_plan]
RESEARCH_TOOLS = [scan_leads, scan_my_book]
