"""Customer book — load past customers, research them concurrently, rank & persist.

Reads a CSV of past customers, runs `research_customer` over all of them in a
small thread pool (free-tier Gemini throttles, so max_workers stays low and the
per-call retry absorbs spikes), keeps only those with a real signal, ranks them,
and persists the hits to a NEW SQLite table — without touching the orchestrator
store schema.
"""
from __future__ import annotations

import csv
import json
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from shared.research import research_customer

DEFAULT_CSV = os.getenv("MOU_CUSTOMERS_CSV", "data/customers.csv")
DEFAULT_DB = os.getenv("MOU_BOOK_DB", "data/book.db")

_SEVERITY_RANK = {"high": 3, "medium": 2, "low": 1}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_customers(path: str | Path = DEFAULT_CSV) -> list[dict]:
    """Load customers from CSV with columns: name, location, services, contact_email."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"customers CSV not found: {p}")
    rows: list[dict] = []
    with p.open(newline="", encoding="utf-8") as f:
        for raw in csv.DictReader(f):
            name = (raw.get("name") or "").strip()
            if not name:
                continue
            rows.append(
                {
                    "name": name,
                    "location": (raw.get("location") or "").strip(),
                    "services": (raw.get("services") or "").strip(),
                    "contact_email": (raw.get("contact_email") or "").strip(),
                }
            )
    return rows


class BookStore:
    """SQLite persistence for found signals. Separate file/table from orchestrator store."""

    def __init__(self, db_path: str | Path = DEFAULT_DB):
        self.db_path = str(db_path)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
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
                CREATE TABLE IF NOT EXISTS book_signals (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    name          TEXT NOT NULL,
                    location      TEXT NOT NULL DEFAULT '',
                    contact_email TEXT NOT NULL DEFAULT '',
                    signal_type   TEXT NOT NULL,
                    severity      TEXT NOT NULL,
                    summary       TEXT NOT NULL DEFAULT '',
                    confidence    REAL NOT NULL DEFAULT 0,
                    evidence      TEXT NOT NULL DEFAULT '[]',
                    created_at    TEXT NOT NULL
                );
                """
            )
            con.commit()
        finally:
            if self._mem_conn is None:
                con.close()

    def save_signal(self, row: dict) -> None:
        con = self._conn()
        try:
            con.execute(
                "INSERT INTO book_signals (name, location, contact_email, signal_type, "
                "severity, summary, confidence, evidence, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    row.get("name", ""),
                    row.get("location", ""),
                    row.get("contact_email", ""),
                    row.get("signal_type", "neutral"),
                    row.get("severity", "low"),
                    row.get("summary", ""),
                    float(row.get("confidence", 0.0) or 0.0),
                    json.dumps(row.get("evidence", [])),
                    _now(),
                ),
            )
            con.commit()
        finally:
            if self._mem_conn is None:
                con.close()

    def all_signals(self) -> list[dict]:
        con = self._conn()
        try:
            rows = con.execute(
                "SELECT * FROM book_signals ORDER BY created_at DESC"
            ).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                d["evidence"] = json.loads(d.get("evidence") or "[]")
                out.append(d)
            return out
        finally:
            if self._mem_conn is None:
                con.close()


def _rank_key(row: dict):
    return (_SEVERITY_RANK.get(row.get("severity"), 0), float(row.get("confidence", 0.0) or 0.0))


def scan_book(
    path: str | Path = DEFAULT_CSV,
    *,
    db_path: str | Path = DEFAULT_DB,
    max_workers: int = 4,
    research_fn: Callable[..., dict] = research_customer,
    persist: bool = True,
) -> dict:
    """Research every customer concurrently, keep the hits, rank, and persist.

    Returns: {scanned, signals_found, ranked: [...], errors: [...]}
    Each ranked row merges the customer fields with the research verdict.
    """
    customers = load_customers(path)
    results: list[dict] = []
    errors: list[dict] = []

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(
                research_fn, c["name"], c.get("location", ""), c.get("services", "")
            ): c
            for c in customers
        }
        for fut in as_completed(futures):
            customer = futures[fut]
            try:
                res = fut.result()
            except Exception as e:  # noqa: BLE001 — a worker should never sink the scan
                errors.append({"name": customer["name"], "error": f"{type(e).__name__}: {e}"})
                continue
            if res.get("error"):
                errors.append({"name": customer["name"], "error": res["error"]})
            if res.get("has_signal"):
                results.append({**customer, **res})

    ranked = sorted(results, key=_rank_key, reverse=True)

    if persist and ranked:
        store = BookStore(db_path)
        for row in ranked:
            store.save_signal(row)

    return {
        "scanned": len(customers),
        "signals_found": len(ranked),
        "ranked": ranked,
        "errors": errors,
    }
