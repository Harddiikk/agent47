"""SDR ledger — SQLite persistence for leads, data points, signals, batches.

Same stdlib-sqlite style as orchestrator/store.py (':memory:' keeps one live
connection). The data_points table is append-only; "changed" means the new
value differs from the latest prior value for (lead, field) — that comparison
IS the delta-detection mechanism. signals dedupe on a hash of
(lead, type, summary) so a rescan never reposts the same opportunity.
"""
from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

LEAD_FIELDS = ("name", "domain", "linkedin_url", "location", "services",
               "contact_name", "contact_email", "last_service", "deal_value", "status")
SIGNAL_STATES = {"new", "posted", "approved", "sent", "dismissed"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sig_hash(lead_id: int, signal_type: str, summary: str) -> str:
    key = f"{lead_id}|{signal_type}|{' '.join((summary or '').lower().split())[:120]}"
    return hashlib.sha1(key.encode()).hexdigest()


class SdrStore:
    def __init__(self, db_path: Path | str):
        self.db_path = str(db_path)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._mem_conn: Optional[sqlite3.Connection] = (
            sqlite3.connect(":memory:", check_same_thread=False)
            if self.db_path == ":memory:" else None
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
                CREATE TABLE IF NOT EXISTS leads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL, domain TEXT NOT NULL DEFAULT '',
                    linkedin_url TEXT NOT NULL DEFAULT '', location TEXT NOT NULL DEFAULT '',
                    services TEXT NOT NULL DEFAULT '', contact_name TEXT NOT NULL DEFAULT '',
                    contact_email TEXT NOT NULL DEFAULT '', last_service TEXT NOT NULL DEFAULT '',
                    deal_value REAL NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT '',
                    resolution TEXT NOT NULL DEFAULT 'unresolved',
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    UNIQUE(name, domain)
                );
                CREATE TABLE IF NOT EXISTS data_points (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lead_id INTEGER NOT NULL, field TEXT NOT NULL, value TEXT NOT NULL,
                    source TEXT NOT NULL, tier TEXT NOT NULL,
                    evidence_url TEXT NOT NULL DEFAULT '', seen_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lead_id INTEGER NOT NULL, signal_type TEXT NOT NULL,
                    summary TEXT NOT NULL, tier TEXT NOT NULL, severity TEXT NOT NULL,
                    matched_offer TEXT NOT NULL DEFAULT '', score REAL NOT NULL DEFAULT 0,
                    state TEXT NOT NULL DEFAULT 'new', sig_hash TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS batches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    csv_path TEXT NOT NULL, total INTEGER NOT NULL DEFAULT 0,
                    resolved INTEGER NOT NULL DEFAULT 0,
                    signals_found INTEGER NOT NULL DEFAULT 0,
                    errors INTEGER NOT NULL DEFAULT 0,
                    started_at TEXT NOT NULL, finished_at TEXT
                );
                """
            )
            con.commit()
        finally:
            if self._mem_conn is None:
                con.close()

    # --- leads ---

    def upsert_lead(self, row: dict) -> dict:
        name = (row.get("name") or "").strip()
        if not name:
            raise ValueError("lead name must be non-empty")
        domain = (row.get("domain") or "").strip().lower()
        now = _now()
        con = self._conn()
        try:
            existing = con.execute(
                "SELECT id FROM leads WHERE name = ? AND domain = ?", (name, domain)
            ).fetchone()
            if existing is None:
                cols = {f: (row.get(f) or ("" if f != "deal_value" else 0)) for f in LEAD_FIELDS}
                cols["name"], cols["domain"] = name, domain
                con.execute(
                    f"INSERT INTO leads ({', '.join(LEAD_FIELDS)}, created_at, updated_at) "
                    f"VALUES ({', '.join('?' * len(LEAD_FIELDS))}, ?, ?)",
                    [*[cols[f] for f in LEAD_FIELDS], now, now],
                )
                lead_id = con.execute("SELECT last_insert_rowid() AS i").fetchone()["i"]
            else:
                lead_id = existing["id"]
                updates = {f: row[f] for f in LEAD_FIELDS
                           if row.get(f) not in (None, "", 0)}
                if updates:
                    sets = ", ".join(f"{f} = ?" for f in updates)
                    con.execute(
                        f"UPDATE leads SET {sets}, updated_at = ? WHERE id = ?",
                        [*updates.values(), now, lead_id],
                    )
            con.commit()
        finally:
            if self._mem_conn is None:
                con.close()
        return self.get_lead(lead_id)  # type: ignore[return-value]

    def get_lead(self, lead_id: int) -> Optional[dict]:
        con = self._conn()
        try:
            r = con.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
            return dict(r) if r else None
        finally:
            if self._mem_conn is None:
                con.close()

    def list_leads(self) -> list[dict]:
        con = self._conn()
        try:
            return [dict(r) for r in con.execute("SELECT * FROM leads ORDER BY id")]
        finally:
            if self._mem_conn is None:
                con.close()

    def set_resolution(self, lead_id: int, resolution: str) -> None:
        con = self._conn()
        try:
            con.execute("UPDATE leads SET resolution = ?, updated_at = ? WHERE id = ?",
                        (resolution, _now(), lead_id))
            con.commit()
        finally:
            if self._mem_conn is None:
                con.close()

    # --- data points (delta ledger) ---

    def latest_point(self, lead_id: int, field: str) -> Optional[dict]:
        con = self._conn()
        try:
            r = con.execute(
                "SELECT * FROM data_points WHERE lead_id = ? AND field = ? "
                "ORDER BY id DESC LIMIT 1", (lead_id, field)).fetchone()
            return dict(r) if r else None
        finally:
            if self._mem_conn is None:
                con.close()

    def add_point(self, lead_id: int, field: str, value: str, source: str,
                  tier: str, evidence_url: str) -> dict:
        prior = self.latest_point(lead_id, field)
        changed = prior is not None and prior["value"] != value
        if prior is not None and prior["value"] == value:
            return {**prior, "changed": False}  # unchanged: don't grow the ledger
        con = self._conn()
        try:
            con.execute(
                "INSERT INTO data_points (lead_id, field, value, source, tier, "
                "evidence_url, seen_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (lead_id, field, value, source, tier, evidence_url, _now()))
            con.commit()
        finally:
            if self._mem_conn is None:
                con.close()
        return {**(self.latest_point(lead_id, field) or {}), "changed": changed}

    # --- signals ---

    def add_signal(self, lead_id: int, signal_type: str, summary: str, tier: str,
                   severity: str, matched_offer: str, score: float) -> Optional[dict]:
        h = _sig_hash(lead_id, signal_type, summary)
        con = self._conn()
        try:
            try:
                con.execute(
                    "INSERT INTO signals (lead_id, signal_type, summary, tier, severity, "
                    "matched_offer, score, sig_hash, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (lead_id, signal_type, summary, tier, severity, matched_offer,
                     score, h, _now()))
                con.commit()
            except sqlite3.IntegrityError:
                return None  # duplicate signal — already known, never repost
            r = con.execute("SELECT * FROM signals WHERE sig_hash = ?", (h,)).fetchone()
            return dict(r)
        finally:
            if self._mem_conn is None:
                con.close()

    def list_signals(self, state: Optional[str] = None) -> list[dict]:
        con = self._conn()
        try:
            if state:
                rows = con.execute(
                    "SELECT * FROM signals WHERE state = ? ORDER BY score DESC", (state,))
            else:
                rows = con.execute("SELECT * FROM signals ORDER BY score DESC")
            return [dict(r) for r in rows]
        finally:
            if self._mem_conn is None:
                con.close()

    def set_signal_state(self, signal_id: int, state: str) -> None:
        if state not in SIGNAL_STATES:
            raise ValueError(f"invalid state '{state}'")
        con = self._conn()
        try:
            con.execute("UPDATE signals SET state = ? WHERE id = ?", (state, signal_id))
            con.commit()
        finally:
            if self._mem_conn is None:
                con.close()

    # --- batches ---

    def create_batch(self, csv_path: str, total: int) -> int:
        con = self._conn()
        try:
            con.execute("INSERT INTO batches (csv_path, total, started_at) VALUES (?, ?, ?)",
                        (csv_path, total, _now()))
            con.commit()
            return con.execute("SELECT last_insert_rowid() AS i").fetchone()["i"]
        finally:
            if self._mem_conn is None:
                con.close()

    def finish_batch(self, batch_id: int, *, resolved: int = 0,
                     signals_found: int = 0, errors: int = 0) -> None:
        con = self._conn()
        try:
            con.execute(
                "UPDATE batches SET resolved = ?, signals_found = ?, errors = ?, "
                "finished_at = ? WHERE id = ?",
                (resolved, signals_found, errors, _now(), batch_id))
            con.commit()
        finally:
            if self._mem_conn is None:
                con.close()

    def get_batch(self, batch_id: int) -> Optional[dict]:
        con = self._conn()
        try:
            r = con.execute("SELECT * FROM batches WHERE id = ?", (batch_id,)).fetchone()
            return dict(r) if r else None
        finally:
            if self._mem_conn is None:
                con.close()
