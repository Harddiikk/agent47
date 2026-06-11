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
                if blob is None or _is_supported(getattr(blob, "mime_type", "")):
                    continue
                name = getattr(blob, "display_name", None) or "attached file"
                mime = getattr(blob, "mime_type", "unknown")
                parts[i] = types.Part(text=(
                    f"[The founder attached '{name}' ({mime}), which this system "
                    f"cannot read. If it is a spreadsheet of leads/customers, ask "
                    f"them to export it as CSV and paste the rows as text, then "
                    f"use import_leads.]"
                ))
                logger.info("attachment_guard: replaced unsupported blob %s (%s)",
                            name, mime)
    except Exception:  # noqa: BLE001 — guard must never break a model call
        logger.exception("attachment_guard failed; passing request through")
    return None
