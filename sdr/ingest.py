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


# Header synonyms seen in real CRM/scraper exports → our canonical lead fields.
# The BUSINESS goes in `name`; people go in `contact_name`.
_HEADER_ALIASES = {
    "name": ("name", "company", "company name", "business", "business name",
             "organization", "organisation", "account", "account name",
             "clinic", "practice", "brand"),
    "contact_name": ("contact_name", "contact name", "contact", "full name",
                     "owner", "person", "lead name"),
    "domain": ("domain", "website", "web site", "url", "site", "company website",
               "domain name", "web"),
    "linkedin_url": ("linkedin_url", "linkedin", "linkedin url", "linkedin profile"),
    "location": ("location", "city", "address", "region", "area", "state",
                 "city/state", "town"),
    "services": ("services", "industry", "category", "niche", "specialty",
                 "vertical", "type", "services offered"),
    "contact_email": ("contact_email", "email", "e-mail", "email address",
                      "work email", "mail"),
    "last_service": ("last_service", "last service", "previous service",
                     "service bought", "past service"),
    "deal_value": ("deal_value", "deal value", "value", "revenue", "amount",
                   "deal size", "contract value"),
    "status": ("status", "stage", "lead status", "deal stage"),
}
_FIRST_NAME = ("first name", "first_name", "firstname", "first")
_LAST_NAME = ("last name", "last_name", "lastname", "last", "surname")


def _build_header_map(fieldnames: list[str], column_map: dict | None) -> dict:
    """Map each raw header -> canonical field ('' = ignore). Explicit
    column_map (the agent's own intelligence) wins over the alias table."""
    explicit = {str(k).strip().lower(): str(v).strip().lower()
                for k, v in (column_map or {}).items()}
    alias_lookup = {a: canon for canon, aliases in _HEADER_ALIASES.items()
                    for a in aliases}
    mapping: dict[str, str] = {}
    for raw in fieldnames or []:
        key = (raw or "").strip().lower()
        if key in explicit and explicit[key] in LEAD_FIELDS:
            mapping[raw] = explicit[key]
        elif key in _FIRST_NAME:
            mapping[raw] = "_first"
        elif key in _LAST_NAME:
            mapping[raw] = "_last"
        else:
            mapping[raw] = alias_lookup.get(key, "")
    return mapping


def save_leads_text(csv_text: str, path: str | Path, *, replace: bool = False,
                    column_map: dict | None = None) -> dict:
    """Persist CSV text (e.g. pasted into the chat) as the leads file.

    Headers are normalized intelligently: common CRM/scraper variants map to
    the canonical schema automatically ('Company'→name, 'Website'→domain,
    'First name'+'Last name'→contact_name, …), and an explicit `column_map`
    ({'their header': 'our field'}) overrides for anything unusual. If no
    business-name column exists, the contact's person name is used as the
    lead name (flagged in the result). Appends + dedupes by default; raises
    ValueError only if nothing is usable.
    """
    text = (csv_text or "").strip()
    if not text:
        raise ValueError("empty CSV text")
    import csv as _csv
    import io

    reader = _csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("could not parse a CSV header from the text")
    hmap = _build_header_map(list(reader.fieldnames), column_map)

    rows, used_person_as_name = [], False
    for raw in reader:
        rec = {f: "" for f in LEAD_FIELDS}
        first = last = ""
        for raw_h, canon in hmap.items():
            val = (raw.get(raw_h) or "").strip()
            if not val or not canon:
                continue
            if canon == "_first":
                first = val
            elif canon == "_last":
                last = val
            elif canon == "deal_value":
                rec[canon] = val.replace("$", "").replace(",", "").strip()
            elif not rec[canon]:  # first non-empty source wins
                rec[canon] = val
        person = " ".join(x for x in (first, last) if x)
        if person and not rec["contact_name"]:
            rec["contact_name"] = person
        if not rec["name"] and rec["contact_name"]:
            rec["name"] = rec["contact_name"]  # person-led list: pitch the person
            used_person_as_name = True
        if rec["name"]:
            rows.append(rec)
    if not rows:
        raise ValueError(
            "no usable lead rows found. Headers seen: "
            + ", ".join(reader.fieldnames)
            + ". Pass column_map={'their header': 'our field'} mapping at least "
              "one column to 'name' (the business) — fields: " + ", ".join(LEAD_FIELDS))

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
            "path": str(p), "replaced": replace,
            "note": ("no business-name column found; used the contact's person "
                     "name as the lead name" if used_person_as_name else "")}
