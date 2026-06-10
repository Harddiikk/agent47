"""Verification — turns a grounded verdict into a confidence tier.

verified : evidence URL fetchable + claim terms corroborated on the page
           + no staleness marker (any year mentioned must be ≤ 2 years old)
probable : evidence URL fetchable but not corroborated
discard  : no/unfetchable evidence, or stale
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Callable, Optional

from sdr.fetch import fetch_text

_STOP = {"the", "a", "an", "in", "of", "and", "new", "has", "their", "its"}


def _key_terms(summary: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]{4,}", (summary or "").lower())
            if t not in _STOP][:8]


def _is_stale(text: str, today_year: int) -> bool:
    years = [int(y) for y in re.findall(r"\b(20\d{2})\b", text)]
    return bool(years) and max(years) < today_year - 1


def verify_grounded(verdict: dict, *, fetch: Callable[[str], str] = fetch_text,
                    today_year: Optional[int] = None) -> str:
    today_year = today_year or datetime.now(timezone.utc).year
    evidence = verdict.get("evidence") or []
    url = next((e.get("source_url", "") for e in evidence
                if str(e.get("source_url", "")).startswith("http")), "")
    if not url:
        return "discard"
    page = fetch(url).lower()
    if not page:
        return "discard"
    summary = verdict.get("summary", "")
    if _is_stale(summary, today_year) or _is_stale(page[:2000], today_year):
        return "discard"
    terms = _key_terms(summary)
    hits = sum(1 for t in terms if t in page)
    return "verified" if terms and hits >= max(2, len(terms) // 3) else "probable"
