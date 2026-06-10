"""Dispatcher — the manager's brain: clients in, plans out.

Planning is done by a tool-free Gemini API call (see planner.py) so it is
inherently safe — the pre-approval pass cannot touch disk, shell, or network.
A workspace directory is reserved per plan now so the post-approval *build*
(GeminiWorker, added in a later step) has an isolated place to work.

Kept as a class with injectable `planner` / `worker_factory` so tests run with
fakes and never hit the Gemini API.
"""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Optional

from orchestrator.planner import GeminiPlanner, PlanResult
from orchestrator.store import PLANNED, Store
from orchestrator.worker import GeminiWorker


def _slug(name: str) -> str:
    s = "".join(c.lower() if c.isalnum() else "_" for c in name).strip("_")
    return s or "client"


class Dispatcher:
    def __init__(
        self,
        store: Store,
        *,
        planner: Optional[GeminiPlanner] = None,
        worker_factory=GeminiWorker,  # used by the post-approval build phase (later step)
        workspaces_root: Path | str = "workspaces",
    ):
        self.store = store
        self.planner = planner or GeminiPlanner()
        self.worker_factory = worker_factory
        self.workspaces_root = Path(workspaces_root)

    # --- clients ---

    def add_client(self, name: str, context: str = "") -> dict:
        """Register a client or append more context to an existing one."""
        return {"ok": True, "client": self.store.add_client(name, context)}

    def list_clients(self) -> dict:
        return {"clients": self.store.list_clients()}

    # --- planning ---

    def dispatch_plan(self, client_name: str, task: str) -> dict:
        """Produce a read-only plan for a client's task (tool-free, awaits approval)."""
        client = self.store.get_client(client_name)
        if client is None:
            return {
                "ok": False,
                "error": f"unknown client '{client_name}'. Add it first with add_client.",
            }

        plan_id = uuid.uuid4().hex[:12]
        workspace = self.workspaces_root / _slug(client_name) / f"plan_{plan_id}"
        workspace.mkdir(parents=True, exist_ok=True)

        result: PlanResult = self.planner.plan(client.get("context", ""), task)

        record = self.store.create_plan(
            plan_id,
            client_name,
            task,
            session_id=None,  # a build session id is assigned after approval
            plan_text=result.text,
            workspace=str(workspace),
            status=PLANNED,
        )
        return {
            "ok": result.success,
            "plan_id": plan_id,
            "status": record["status"],
            "plan": result.text,
            "workspace": str(workspace),
            "error": None if result.success else result.error,
        }

    # --- reporting ---

    def list_plans(self, status: Optional[str] = None) -> dict:
        plans = self.store.list_plans(status)
        for p in plans:  # trim text in list views to keep payloads small
            text = p.get("plan_text") or ""
            p["plan_excerpt"] = (text[:280] + "…") if len(text) > 280 else text
            p.pop("plan_text", None)
        return {"plans": plans}

    def get_plan(self, plan_id: str) -> dict:
        plan = self.store.get_plan(plan_id)
        if plan is None:
            return {"ok": False, "error": f"no plan with id '{plan_id}'"}
        return {"ok": True, "plan": plan}
