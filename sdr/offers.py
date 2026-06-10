"""Offer catalog + signal→offer matcher. Catalog is config (data/offers.json),
so the agency can change what it sells without touching code."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

DEFAULT_OFFERS_PATH = "data/offers.json"

_FALLBACK_BY_TYPE = {
    "expansion": "GBP / Google Maps setup + Local SEO",
    "risk": "Reputation Management",
    "health": "Google Ads Management",
    "neutral": "AI Automation Audit",
    "update": "GBP / Google Maps setup + Local SEO",
}

_BUILTIN = [
    {"name": "GBP / Google Maps setup + Local SEO",
     "triggers": ["location", "clinic", "office", "opening", "opened", "branch", "expansion"]},
    {"name": "Service Landing Page + Google Ads",
     "triggers": ["machine", "equipment", "laser", "invisalign", "offering", "treatment"]},
    {"name": "Reputation Management",
     "triggers": ["review", "reviews", "rating", "stars", "complaint", "reputation"]},
    {"name": "AI Receptionist / Front-desk Automation",
     "triggers": ["hiring", "front desk", "receptionist", "job", "staff", "recruit"]},
    {"name": "Booking Automation",
     "triggers": ["booking", "appointment", "schedule", "scheduling"]},
    {"name": "Google Ads Management",
     "triggers": ["ads", "advertising", "campaign", "promotion"]},
]


def load_offers(path: str | Path = DEFAULT_OFFERS_PATH) -> list[dict]:
    """Load the catalog; fall back to the builtin copy if the file is absent/bad."""
    try:
        data = json.loads(Path(path).read_text())
        if isinstance(data, list) and all("name" in o for o in data):
            return data
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    return list(_BUILTIN)


def match_offer(signal_type: str, summary: str,
                offers: Optional[list[dict]] = None) -> str:
    """Best offer for a signal: most trigger-keyword hits in the summary;
    falls back to a sensible default per signal type. Never returns ''."""
    offers = offers if offers is not None else load_offers()
    text = (summary or "").lower()
    best, best_hits = "", 0
    for offer in offers:
        hits = sum(1 for t in offer.get("triggers", []) if t in text)
        if hits > best_hits:
            best, best_hits = offer["name"], hits
    return best or _FALLBACK_BY_TYPE.get(signal_type, "AI Automation Audit")
