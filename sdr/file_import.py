"""Turn spreadsheet files dropped into the chat directly into imported leads.

Product principle: built for everyone, not developers. A founder shouldn't
need to know what a CSV is — they drop the Excel file their CRM exported and
the agent says "got your leads." The attachment guard calls try_import_blob()
for spreadsheet attachments; we parse the bytes (openpyxl for .xlsx, text
decode for CSV), reuse the smart header mapper in save_leads_text, and report.

A content-hash ledger (data/.imported_files.json) makes imports idempotent:
the same attachment replayed from session history on every later turn is
recognized and skipped, not re-imported.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path
from typing import Optional

from sdr.ingest import save_leads_text

SPREADSHEET_MIMES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.ms-excel": "xls_or_csv",  # often used loosely for CSVs too
    "text/csv": "csv",
    "application/csv": "csv",
}

_HASH_LEDGER = "data/.imported_files.json"
_MAX_ROWS = 5000


def _ledger_path() -> Path:
    return Path(_HASH_LEDGER)


def _seen(digest: str) -> Optional[dict]:
    try:
        return json.loads(_ledger_path().read_text()).get(digest)
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def _remember(digest: str, summary: dict) -> None:
    path = _ledger_path()
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError, ValueError):
        data = {}
    data[digest] = summary
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def csv_text_from_xlsx(data: bytes) -> str:
    """First worksheet of an .xlsx → CSV text (header row first)."""
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    ws = wb.worksheets[0]
    out = io.StringIO()
    writer = csv.writer(out)
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i > _MAX_ROWS:
            break
        writer.writerow(["" if c is None else str(c) for c in row])
    wb.close()
    return out.getvalue()


def try_import_blob(data: bytes, mime_type: str, filename: str = "") -> Optional[dict]:
    """Import a spreadsheet attachment as leads. Returns a result dict, or
    None when the mime type isn't a spreadsheet. Never raises."""
    kind = SPREADSHEET_MIMES.get((mime_type or "").lower())
    if kind is None or not data:
        return None
    digest = hashlib.sha1(data).hexdigest()
    prior = _seen(digest)
    if prior:
        return {**prior, "already_imported": True}

    try:
        if kind == "xlsx":
            csv_text = csv_text_from_xlsx(data)
        else:
            try:  # 'application/vnd.ms-excel' is frequently a CSV in disguise
                csv_text = csv_text_from_xlsx(data)
            except Exception:  # noqa: BLE001
                csv_text = data.decode("utf-8", errors="replace")
        result = save_leads_text(csv_text, "data/leads.csv")
    except ValueError as e:
        return {"ok": False, "filename": filename, "error": str(e)}
    except Exception as e:  # noqa: BLE001 — corrupt files must not break the chat
        return {"ok": False, "filename": filename,
                "error": f"could not read the file ({type(e).__name__})"}

    summary = {"ok": True, "filename": filename, "imported": result["imported"],
               "total_in_file": result["total_in_file"],
               "note": result.get("note", "")}
    _remember(digest, summary)
    return summary
