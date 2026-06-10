"""Collectors. Website snapshot/diff is the deterministic ✅ tier; grounded
search (reusing shared/research.py) is the ⚠️ tier pending verification."""
from __future__ import annotations

import re
from typing import Callable

from sdr.fetch import fetch_text
from sdr.store import SdrStore
from shared.research import research_customer

PAGES = ("", "/services", "/locations")  # homepage + the two money pages
_SNAPSHOT_CHARS = 5000
_EXCERPT_CHARS = 400

# Dynamic-widget noise (store hours, distances, open/closed status) re-renders
# differently on every fetch and must not count as a website "change".
_VOLATILE = (
    re.compile(r"\b\d{1,2}:\d{2}\s*(?:am|pm)?\b", re.IGNORECASE),   # 7:00am
    re.compile(r"\b\d+(?:\.\d+)?\s*mi\b", re.IGNORECASE),           # 7 mi
    re.compile(r"\b(?:open|opens|closed|closes)\b", re.IGNORECASE),  # status words
    re.compile(r"\b(?:mon|monday|tue|tues|tuesday|wed|wednesday|thu|thur|thurs|thursday"
               r"|fri|friday|sat|saturday|sun|sunday)\b", re.IGNORECASE),
)


def scrub_volatile(text: str) -> str:
    """Strip dynamic-widget tokens so snapshots only diff on real content."""
    for pat in _VOLATILE:
        text = pat.sub(" ", text)
    return " ".join(text.split())


def diff_excerpt(old: str, new: str) -> str:
    """Sentences present in `new` but not `old`, joined, capped. Deterministic."""
    old_set = {s.strip() for s in old.split(".") if s.strip()}
    added = [s.strip() for s in new.split(".") if s.strip() and s.strip() not in old_set]
    return (". ".join(added))[:_EXCERPT_CHARS]


def collect_website(lead: dict, store: SdrStore, *,
                    fetch: Callable[[str], str] = fetch_text) -> dict:
    """Snapshot key pages; on rescan, report changed pages with a diff excerpt.
    First sighting of a page is a baseline, not a change."""
    domain = (lead.get("domain") or "").strip().lower()
    if not domain:
        return {"changes": [], "pages_seen": 0}
    base = domain if domain.startswith("http") else f"https://{domain}"
    changes, seen = [], 0
    for page in PAGES:
        text = fetch(base + page)
        if not text:
            continue
        seen += 1
        snapshot = scrub_volatile(text)[:_SNAPSHOT_CHARS]
        field = f"website:{page.strip('/') or 'home'}"
        prior = store.latest_point(lead["id"], field)
        point = store.add_point(lead["id"], field, snapshot, "website", "verified",
                                base + page)
        if point.get("changed") and prior is not None:
            changes.append({"field": field, "url": base + page,
                            "excerpt": diff_excerpt(prior["value"], snapshot)})
    return {"changes": changes, "pages_seen": seen}


def collect_grounded(lead: dict, *,
                     research_fn: Callable[..., dict] = research_customer) -> dict:
    """Grounded web research via the proven shared/research.py path."""
    return research_fn(lead.get("name", ""), lead.get("location", ""),
                       lead.get("services", ""))
