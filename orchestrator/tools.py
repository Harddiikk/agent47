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


MANAGER_TOOLS = [
    add_client,
    list_clients,
    dispatch_plan,
    list_plans,
    get_plan,
    scan_my_book,
]
