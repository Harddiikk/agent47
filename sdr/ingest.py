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


def save_leads_text(csv_text: str, path: str | Path, *, replace: bool = False) -> dict:
    """Persist CSV text (e.g. pasted into the chat) as the leads file.

    Accepts a header row plus data rows; tolerant like load_leads (only `name`
    required). Appends to an existing file by default — never silently drops
    the book — or replaces it when asked. Returns counts, never raises for
    bad rows (they're skipped); raises ValueError only if nothing is usable.
    """
    text = (csv_text or "").strip()
    if not text:
        raise ValueError("empty CSV text")
    import csv as _csv
    import io

    reader = _csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or "name" not in [f.strip().lower() for f in reader.fieldnames]:
        raise ValueError("first line must be a CSV header including a 'name' column")
    rows = []
    for raw in reader:
        name = (raw.get("name") or "").strip()
        if not name:
            continue
        rows.append({f: (raw.get(f) or "").strip() for f in LEAD_FIELDS} | {"name": name})
    if not rows:
        raise ValueError("no usable lead rows found (need at least a name per row)")

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    existing: list[dict] = []
    if p.exists() and not replace:
        existing = load_leads(p)
        seen = {(r["name"].lower(), r["domain"].lower()) for r in existing}
        rows = [r for r in rows
                if (r["name"].lower(), r.get("domain", "").lower()) not in seen]

    with p.open("w", newline="", encoding="utf-8") as f:
        writer = _csv.DictWriter(f, fieldnames=list(LEAD_FIELDS))
        writer.writeheader()
        for r in existing + rows:
            writer.writerow({f: r.get(f, "") for f in LEAD_FIELDS})
    return {"imported": len(rows), "total_in_file": len(existing) + len(rows),
            "path": str(p), "replaced": replace}
