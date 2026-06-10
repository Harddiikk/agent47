"""Lead CSV ingestion — tolerant rich-schema loader + batch creation."""
from __future__ import annotations

import csv
from pathlib import Path

from sdr.store import LEAD_FIELDS, SdrStore


def load_leads(path: str | Path) -> list[dict]:
    """Load leads from CSV. Only `name` is required; unknown columns ignored,
    missing optionals default to ''/0. `deal_value` is coerced to float."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"leads CSV not found: {p}")
    rows: list[dict] = []
    with p.open(newline="", encoding="utf-8") as f:
        for raw in csv.DictReader(f):
            name = (raw.get("name") or "").strip()
            if not name:
                continue
            row = {f: (raw.get(f) or "").strip() for f in LEAD_FIELDS}
            row["name"] = name
            try:
                row["deal_value"] = float(row["deal_value"] or 0)
            except ValueError:
                row["deal_value"] = 0.0
            rows.append(row)
    return rows


def ingest_csv(store: SdrStore, path: str | Path) -> dict:
    """Upsert every lead and open a batch. Returns {batch_id, leads}."""
    rows = load_leads(path)
    leads = [store.upsert_lead(r) for r in rows]
    batch_id = store.create_batch(str(path), total=len(leads))
    return {"batch_id": batch_id, "leads": leads}
