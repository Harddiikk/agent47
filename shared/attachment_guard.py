"""Strip model-unsupported file attachments before every Gemini call.

Why: the ADK web UI lets the founder attach any file (e.g. .xlsx). Gemini
rejects unsupported MIME types with 400 INVALID_ARGUMENT — and because the
attachment lives in session history, EVERY subsequent turn replays it and the
whole session becomes unusable ("poisoned"). This before_model_callback runs
on each request, removes unsupported inline blobs (history included), and
replaces them with a text note so the agent can respond helpfully ("paste it
as CSV") instead of erroring.

Attach to every agent: sub-agent transfers replay the same session contents,
so guarding only the root would still 400 inside specialists.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Gemini-supported inline MIME families/types (allowlist — unknown means strip).
_ALLOWED_PREFIXES = ("image/", "audio/", "video/", "text/")
_ALLOWED_EXACT = {
    "application/pdf",
    "application/json",
    "application/x-javascript",
    "application/x-python",
}


def _is_supported(mime_type: str) -> bool:
    mt = (mime_type or "").lower()
    return mt.startswith(_ALLOWED_PREFIXES) or mt in _ALLOWED_EXACT


def strip_unsupported_attachments(callback_context=None, llm_request=None):
    """ADK before_model_callback: mutate llm_request in place, return None.

    Returning None tells ADK to continue with the (now sanitized) request.
    """
    if llm_request is None or not getattr(llm_request, "contents", None):
        return None
    try:
        from google.genai import types

        for content in llm_request.contents:
            parts = getattr(content, "parts", None) or []
            for i, part in enumerate(parts):
                blob = getattr(part, "inline_data", None)
                if blob is None:
                    continue
                mime = getattr(blob, "mime_type", "") or ""
                name = getattr(blob, "display_name", None) or "attached file"

                # Spreadsheets (xlsx/csv) become imported leads — simple for
                # everyone: drop the file your CRM exported, done.
                from sdr.file_import import SPREADSHEET_MIMES, try_import_blob

                if mime.lower() in SPREADSHEET_MIMES:
                    result = try_import_blob(getattr(blob, "data", b""), mime, name)
                    parts[i] = types.Part(text=_import_note(name, result))
                    logger.info("attachment_guard: spreadsheet %s -> %s", name, result)
                    continue

                if _is_supported(mime):
                    continue
                parts[i] = types.Part(text=(
                    f"[The founder attached '{name}' ({mime}), which this system "
                    f"cannot read. Spreadsheets (.xlsx/.csv) are imported "
                    f"automatically — for anything else, ask them to paste the "
                    f"content as text.]"
                ))
                logger.info("attachment_guard: replaced unsupported blob %s (%s)",
                            name, mime)
    except Exception:  # noqa: BLE001 — guard must never break a model call
        logger.exception("attachment_guard failed; passing request through")
    return None


def _import_note(name: str, result) -> str:
    """The text the model sees in place of a spreadsheet attachment."""
    if not result:
        return f"[The founder attached '{name}' but it contained no data.]"
    if result.get("already_imported"):
        return (f"[Spreadsheet '{name}' was already imported earlier "
                f"({result.get('imported', 0)} leads). Do not re-import.]")
    if result.get("ok"):
        note = f" Note: {result['note']}." if result.get("note") else ""
        return (f"[Spreadsheet '{name}' received: {result['imported']} leads "
                f"imported into the lead book ({result['total_in_file']} total)."
                f"{note} Tell the founder the counts in one line, then START THE "
                f"SCAN IMMEDIATELY by calling scan_leads with NO arguments (the "
                f"file is already merged into the lead book; never pass the "
                f"uploaded filename as a path). Do not ask for permission.]")
    return (f"[Spreadsheet '{name}' could not be imported: "
            f"{result.get('error', 'unknown error')}. Tell the founder what "
            f"went wrong in plain language and how to fix it.]")
