"""Persistent state for the orchestrator — SQLite, stdlib only.

Replaces the in-memory signal store that resets on restart. Holds the two
things the manager needs to survive restarts and a long approval round-trip:

  - clients : name + accumulated context the founder gives in the chat.
  - plans   : each dispatched task — its Gemini session id (to resume after
              approval), the plan text, the workspace, and a status that walks
              planned → approved → building → done / failed / rejected.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Plan lifecycle.
PLANNED = "planned"
APPROVED = "approved"
BUILDING = "building"
DONE = "done"
FAILED = "failed"
REJECTED = "rejected"

PLAN_STATUSES = {PLANNED, APPROVED, BUILDING, DONE, FAILED, REJECTED}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    """Thin SQLite wrapper. Pass ':memory:' or a tmp path in tests."""

    def __init__(self, db_path: Path | str):
        self.db_path = str(db_path)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        # For ':memory:' we must keep a single connection alive for the DB to persist.
        self._mem_conn: Optional[sqlite3.Connection] = (
            sqlite3.connect(":memory:") if self.db_path == ":memory:" else None
        )
        if self._mem_conn is not None:
            self._mem_conn.row_factory = sqlite3.Row
        self._init_schema()

    def _conn(self) -> sqlite3.Connection:
        if self._mem_conn is not None:
            return self._mem_conn
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        return con

    def _init_schema(self) -> None:
        con = self._conn()
        try:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS clients (
                    name       TEXT PRIMARY KEY,
                    context    TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS plans (
                    id          TEXT PRIMARY KEY,
                    client_name TEXT NOT NULL,
                    task        TEXT NOT NULL,
                    session_id  TEXT,
                    plan_text   TEXT NOT NULL DEFAULT '',
                    workspace   TEXT NOT NULL DEFAULT '',
                    status      TEXT NOT NULL DEFAULT 'planned',
                    created_at  TEXT NOT NULL,
                    updated_at  TEXT NOT NULL
                );
                """
            )
            con.commit()
        finally:
            if self._mem_conn is None:
                con.close()

    # --- clients ---

    def add_client(self, name: str, context: str = "") -> dict:
        """Create a client, or append context to an existing one (idempotent intake)."""
        name = name.strip()
        if not name:
            raise ValueError("client name must be non-empty")
        context = context.strip()
        now = _now()
        con = self._conn()
        try:
            existing = con.execute(
                "SELECT context FROM clients WHERE name = ?", (name,)
            ).fetchone()
            if existing is None:
                con.execute(
                    "INSERT INTO clients (name, context, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?)",
                    (name, context, now, now),
                )
            else:
                merged = existing["context"]
                if context:
                    merged = f"{merged}\n\n{context}".strip()
                con.execute(
                    "UPDATE clients SET context = ?, updated_at = ? WHERE name = ?",
                    (merged, now, name),
                )
            con.commit()
        finally:
            if self._mem_conn is None:
                con.close()
        return self.get_client(name)  # type: ignore[return-value]

    def get_client(self, name: str) -> Optional[dict]:
        con = self._conn()
        try:
            row = con.execute(
                "SELECT * FROM clients WHERE name = ?", (name.strip(),)
            ).fetchone()
            return dict(row) if row else None
        finally:
            if self._mem_conn is None:
                con.close()

    def list_clients(self) -> list[dict]:
        con = self._conn()
        try:
            rows = con.execute("SELECT * FROM clients ORDER BY created_at").fetchall()
            return [dict(r) for r in rows]
        finally:
            if self._mem_conn is None:
                con.close()

    # --- plans ---

    def create_plan(
        self,
        plan_id: str,
        client_name: str,
        task: str,
        *,
        session_id: Optional[str] = None,
        plan_text: str = "",
        workspace: str = "",
        status: str = PLANNED,
    ) -> dict:
        if status not in PLAN_STATUSES:
            raise ValueError(f"invalid status '{status}'")
        now = _now()
        con = self._conn()
        try:
            con.execute(
                "INSERT INTO plans (id, client_name, task, session_id, plan_text, "
                "workspace, status, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (plan_id, client_name, task, session_id, plan_text, workspace, status, now, now),
            )
            con.commit()
        finally:
            if self._mem_conn is None:
                con.close()
        return self.get_plan(plan_id)  # type: ignore[return-value]

    def get_plan(self, plan_id: str) -> Optional[dict]:
        con = self._conn()
        try:
            row = con.execute("SELECT * FROM plans WHERE id = ?", (plan_id,)).fetchone()
            return dict(row) if row else None
        finally:
            if self._mem_conn is None:
                con.close()

    def set_plan_status(self, plan_id: str, status: str) -> Optional[dict]:
        if status not in PLAN_STATUSES:
            raise ValueError(f"invalid status '{status}'")
        con = self._conn()
        try:
            con.execute(
                "UPDATE plans SET status = ?, updated_at = ? WHERE id = ?",
                (status, _now(), plan_id),
            )
            con.commit()
        finally:
            if self._mem_conn is None:
                con.close()
        return self.get_plan(plan_id)

    def list_plans(self, status: Optional[str] = None) -> list[dict]:
        con = self._conn()
        try:
            if status is not None:
                rows = con.execute(
                    "SELECT * FROM plans WHERE status = ? ORDER BY created_at DESC",
                    (status,),
                ).fetchall()
            else:
                rows = con.execute(
                    "SELECT * FROM plans ORDER BY created_at DESC"
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            if self._mem_conn is None:
                con.close()
