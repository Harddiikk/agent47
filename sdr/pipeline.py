"""The SDR batch pipeline: ingest → resolve → collect → verify → delta →
offer-match → score → deliver. Per-lead failures become counts, never crashes."""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Optional

from sdr.collect import collect_grounded, collect_website
from sdr.fetch import fetch_text
from sdr.ingest import ingest_csv
from sdr.offers import load_offers, match_offer
from sdr.resolve import resolve_lead
from sdr.slack import deliver_results, digest_blocks, signal_card_blocks
from sdr.store import SdrStore
from sdr.verify import verify_grounded
from shared.outreach import draft_outreach
from shared.research import research_customer

DEFAULT_DB = os.getenv("SDR_DB_PATH", "data/sdr.db")
_SEV_RANK = {"high": 3, "medium": 2, "low": 1}


def _score(severity: str, confidence: float, tier: str, deal_value: float) -> float:
    return (_SEV_RANK.get(severity, 1) * 2 + float(confidence or 0)
            + (1.0 if tier == "verified" else 0.0)
            + min(float(deal_value or 0) / 10000.0, 1.0))


def _process_lead(lead: dict, store: SdrStore, fetch, research_fn, offers) -> dict:
    """Resolve + enrich one lead. Returns counters + any new signals."""
    out = {"resolved": 0, "unresolved": 0, "errors": 0, "signals": []}
    res = resolve_lead(lead, fetch=fetch)
    store.set_resolution(lead["id"], res["resolution"])
    if res["resolution"] == "unresolved":
        out["unresolved"] = 1
        return out  # never pitch an unresolved lead (spec hard gate)
    out["resolved"] = 1

    # Deterministic tier: website diffs (✅, free) — emits 'update' signals.
    # Two noise gates: the excerpt must contain an offer-trigger keyword (a diff
    # with no sellable hook isn't a pitch), and one update per lead per 30 days.
    trigger_words = {t for o in offers for t in o.get("triggers", [])}
    site = collect_website(lead, store, fetch=fetch)
    for chg in site["changes"]:
        if not chg["excerpt"]:
            continue
        excerpt_lower = chg["excerpt"].lower()
        if not any(t in excerpt_lower for t in trigger_words):
            continue
        if store.has_recent_signal(lead["id"], "update"):
            continue
        summary = f"Website {chg['field'].split(':')[1]} page changed: {chg['excerpt']}"
        sig = store.add_signal(lead["id"], "update", summary, "verified", "medium",
                               match_offer("update", chg["excerpt"], offers),
                               _score("medium", 0.9, "verified", lead.get("deal_value", 0)))
        if sig:
            out["signals"].append({**sig, "evidence_url": chg["url"]})

    # Grounded tier (⚠️ until verified). Cost rule: only for resolved leads.
    verdict = collect_grounded(lead, research_fn=research_fn)
    if verdict.get("error"):
        out["errors"] = 1
    if verdict.get("has_signal"):
        stype = verdict.get("signal_type", "neutral")
        if store.has_recent_signal(lead["id"], stype):
            return out  # cooldown: same-type signal already live — rewording can't repost
        tier = verify_grounded(verdict, fetch=fetch)
        if tier in ("verified", "probable"):
            ev = verdict.get("evidence") or []
            ev_url = next((e.get("source_url", "") for e in ev
                           if str(e.get("source_url", "")).startswith("http")), "")
            store.add_point(lead["id"], "grounded:summary", verdict.get("summary", ""),
                            "grounded", tier, ev_url)
            sig = store.add_signal(
                lead["id"], verdict.get("signal_type", "neutral"),
                verdict.get("summary", ""), tier, verdict.get("severity", "low"),
                match_offer(verdict.get("signal_type", ""), verdict.get("summary", ""),
                            offers),
                _score(verdict.get("severity", "low"), verdict.get("confidence", 0),
                       tier, lead.get("deal_value", 0)))
            if sig:
                out["signals"].append({**sig, "evidence_url": ev_url})
    return out


def run_scan(csv_path: str | Path, *, store: Optional[SdrStore] = None,
             db_path: str | Path = DEFAULT_DB,
             fetch: Callable[[str], str] = fetch_text,
             research_fn: Callable[..., dict] = research_customer,
             draft_fn: Callable[..., str] = draft_outreach,
             max_workers: int = 4, deliver: bool = True) -> dict:
    """Run one SDR batch. Returns a summary dict; never raises for lead failures."""
    store = store or SdrStore(db_path)
    offers = load_offers()
    batch = ingest_csv(store, csv_path)
    leads = batch["leads"]

    counters = {"resolved": 0, "unresolved": 0, "errors": 0}
    new_signals: list[dict] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_process_lead, lead, store, fetch, research_fn, offers):
                   lead for lead in leads}
        for fut in as_completed(futures):
            try:
                r = fut.result()
            except Exception:  # noqa: BLE001 — one lead must never sink the batch
                counters["errors"] += 1
                continue
            for k in ("resolved", "unresolved", "errors"):
                counters[k] += r[k]
            for sig in r["signals"]:
                lead = futures[fut]
                new_signals.append({"lead": lead, "signal": sig})

    new_signals.sort(key=lambda x: x["signal"].get("score", 0), reverse=True)

    cards, top = [], []
    for item in new_signals:
        lead, sig = item["lead"], item["signal"]
        draft = draft_fn({"name": lead["name"]},
                         {"summary": f"{sig['summary']} "
                                     f"(suggested service: {sig['matched_offer']})"})
        cards.append(signal_card_blocks(lead, sig, draft))
        store.set_signal_state(sig["id"], "posted")
        top.append({"name": lead["name"], "summary": sig["summary"],
                    "tier": sig["tier"], "severity": sig["severity"],
                    "offer": sig["matched_offer"], "score": sig["score"],
                    "evidence_url": sig.get("evidence_url", ""), "draft": draft})

    summary = {"batch_id": batch["batch_id"], "total": len(leads), **counters,
               "signals_found": len(new_signals)}
    store.finish_batch(batch["batch_id"], resolved=counters["resolved"],
                       signals_found=len(new_signals), errors=counters["errors"])
    delivery = (deliver_results(digest_blocks(summary), cards)
                if deliver else {"mode": "skipped", "delivered": 0})
    return {**summary, "delivery": delivery, "top": top}
