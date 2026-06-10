"""Tests for the orchestrator persistent store (SQLite)."""
import pytest

from orchestrator.store import DONE, PLANNED, REJECTED, Store


@pytest.fixture
def store():
    return Store(":memory:")


# --- clients ---


def test_add_and_get_client(store):
    store.add_client("acme", "B2B SaaS, billing automation")
    c = store.get_client("acme")
    assert c["name"] == "acme"
    assert "billing" in c["context"]
    assert c["created_at"] and c["updated_at"]


def test_add_client_accumulates_context(store):
    store.add_client("acme", "first detail")
    store.add_client("acme", "second detail")
    c = store.get_client("acme")
    assert "first detail" in c["context"]
    assert "second detail" in c["context"]


def test_add_client_rejects_blank(store):
    with pytest.raises(ValueError):
        store.add_client("   ")


def test_get_unknown_client_is_none(store):
    assert store.get_client("nobody") is None


def test_list_clients(store):
    store.add_client("acme")
    store.add_client("globex")
    names = {c["name"] for c in store.list_clients()}
    assert names == {"acme", "globex"}


# --- plans ---


def test_create_and_get_plan(store):
    store.add_client("acme")
    p = store.create_plan(
        "p1", "acme", "build a dashboard", session_id="sess-1", plan_text="the plan"
    )
    assert p["id"] == "p1"
    assert p["status"] == PLANNED
    assert p["session_id"] == "sess-1"
    assert store.get_plan("p1")["plan_text"] == "the plan"


def test_create_plan_rejects_bad_status(store):
    with pytest.raises(ValueError):
        store.create_plan("p1", "acme", "x", status="bogus")


def test_set_plan_status(store):
    store.create_plan("p1", "acme", "x")
    updated = store.set_plan_status("p1", DONE)
    assert updated["status"] == DONE


def test_set_plan_status_rejects_bad(store):
    store.create_plan("p1", "acme", "x")
    with pytest.raises(ValueError):
        store.set_plan_status("p1", "nope")


def test_list_plans_filter_by_status(store):
    store.create_plan("p1", "acme", "a", status=PLANNED)
    store.create_plan("p2", "acme", "b", status=PLANNED)
    store.create_plan("p3", "acme", "c", status=REJECTED)
    assert len(store.list_plans()) == 3
    assert len(store.list_plans(PLANNED)) == 2
    assert len(store.list_plans(REJECTED)) == 1


def test_persistence_across_connections(tmp_path):
    db = tmp_path / "state.db"
    s1 = Store(db)
    s1.add_client("acme", "ctx")
    s1.create_plan("p1", "acme", "task", session_id="s")
    # New Store instance / new connection sees the persisted data.
    s2 = Store(db)
    assert s2.get_client("acme")["context"] == "ctx"
    assert s2.get_plan("p1")["session_id"] == "s"
