"""Tests for the Dispatcher — uses a fake planner so no Gemini API calls happen."""
from pathlib import Path

from orchestrator.dispatcher import Dispatcher
from orchestrator.planner import PlanResult
from orchestrator.store import PLANNED, Store


class FakePlanner:
    """Stand-in for GeminiPlanner. Records the inputs; returns a canned result."""

    last_context: str = ""
    last_task: str = ""

    def __init__(self, result: PlanResult):
        self._result = result

    def plan(self, context: str, task: str) -> PlanResult:
        FakePlanner.last_context = context
        FakePlanner.last_task = task
        return self._result


def make_dispatcher(tmp_path, *, success=True, text="THE PLAN", error=""):
    result = PlanResult(success=success, text=text, model="fake", error=error)
    return Dispatcher(
        Store(":memory:"),
        planner=FakePlanner(result),
        workspaces_root=tmp_path / "workspaces",
    )


def test_dispatch_plan_happy_path(tmp_path):
    d = make_dispatcher(tmp_path)
    d.add_client("acme", "B2B billing client")
    out = d.dispatch_plan("acme", "build a renewal dashboard")

    assert out["ok"] is True
    assert out["plan"] == "THE PLAN"
    assert out["status"] == PLANNED
    assert out["plan_id"]
    # an isolated workspace is reserved under the client slug for the later build
    assert Path(out["workspace"]).is_dir()
    assert "acme" in out["workspace"]


def test_dispatch_plan_feeds_context_and_task_to_planner(tmp_path):
    d = make_dispatcher(tmp_path)
    d.add_client("acme", "B2B billing client")
    d.dispatch_plan("acme", "build a renewal dashboard")
    assert "B2B billing client" in FakePlanner.last_context
    assert FakePlanner.last_task == "build a renewal dashboard"


def test_dispatch_plan_unknown_client(tmp_path):
    d = make_dispatcher(tmp_path)
    out = d.dispatch_plan("ghost", "do something")
    assert out["ok"] is False
    assert "unknown client" in out["error"].lower()


def test_dispatch_plan_persists_record(tmp_path):
    d = make_dispatcher(tmp_path)
    d.add_client("acme")
    out = d.dispatch_plan("acme", "task")
    stored = d.store.get_plan(out["plan_id"])
    assert stored is not None
    assert stored["plan_text"] == "THE PLAN"
    assert stored["status"] == PLANNED
    # no build session yet — assigned after approval
    assert stored["session_id"] is None


def test_dispatch_plan_planner_failure_surfaces(tmp_path):
    d = make_dispatcher(tmp_path, success=False, text="", error="503 UNAVAILABLE")
    d.add_client("acme")
    out = d.dispatch_plan("acme", "task")
    assert out["ok"] is False
    assert "503" in out["error"]


def test_list_plans_excerpts_long_text(tmp_path):
    d = make_dispatcher(tmp_path, text="x" * 500)
    d.add_client("acme")
    d.dispatch_plan("acme", "task")
    listed = d.list_plans()["plans"]
    assert len(listed) == 1
    assert listed[0]["plan_excerpt"].endswith("…")
    assert "plan_text" not in listed[0]  # trimmed from list view


def test_list_clients(tmp_path):
    d = make_dispatcher(tmp_path)
    d.add_client("acme")
    d.add_client("globex")
    assert {c["name"] for c in d.list_clients()["clients"]} == {"acme", "globex"}
