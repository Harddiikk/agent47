"""Entity resolution — confirm the domain actually belongs to this lead.

The correctness gate from the spec: unresolved leads are never pitched.
verified  : ≥60% of the lead's name tokens appear on the homepage
weak      : some name token OR the lead's city appears
unresolved: no domain / fetch failed / nothing matches
"""
from __future__ import annotations

import re
from typing import Callable

from sdr.fetch import fetch_text

_STOP = {"the", "and", "llc", "inc", "co", "of"}


def _tokens(name: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", (name or "").lower())
            if len(t) > 2 and t not in _STOP]


def resolve_lead(lead: dict, *, fetch: Callable[[str], str] = fetch_text) -> dict:
    domain = (lead.get("domain") or "").strip().lower()
    if not domain:
        return {"resolution": "unresolved", "reason": "no domain provided"}
    url = domain if domain.startswith("http") else f"https://{domain}"
    page = fetch(url).lower()
    if not page:
        return {"resolution": "unresolved", "reason": f"could not fetch {url}"}
    toks = _tokens(lead.get("name", ""))
    hits = sum(1 for t in toks if t in page)
    if toks and hits / len(toks) >= 0.6:
        return {"resolution": "verified", "reason": f"{hits}/{len(toks)} name tokens on site"}
    city = (lead.get("location") or "").split(",")[0].strip().lower()
    if hits or (city and city in page):
        return {"resolution": "weak", "reason": "partial name/location match"}
    return {"resolution": "unresolved", "reason": "site content does not match lead"}
