"""Headless demo runner — the full book-scan pipeline, printed as a clean table.

Run:  python -m scripts.scan      (or `make scan`)

This is the reliable demo path if the ADK web UI is flaky during recording.
Requires GEMINI_API_KEY. Optional: SLACK_WEBHOOK_URL or Composio env for real
Slack delivery; otherwise it prints the formatted Slack blocks.
"""
from __future__ import annotations

import os
import sys


def _load_env() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except Exception:  # noqa: BLE001 — dotenv is optional
        pass


def _hr(char: str = "─", n: int = 78) -> str:
    return char * n


def main() -> int:
    _load_env()
    if not os.getenv("GEMINI_API_KEY"):
        print("⚠️  GEMINI_API_KEY is not set. Set it in .env or the environment.")
        return 2

    from shared.outreach import scan_and_deliver

    print("\n🕴️  Agent 47 — scanning your customer book for expansion signals…\n")
    result = scan_and_deliver()

    print(_hr("═"))
    print(
        f"  Scanned: {result['scanned']} customers   |   "
        f"Signals found: {result['signals_found']}   |   "
        f"Delivery: {result['delivery'].get('mode')}"
    )
    print(_hr("═"))

    top = result.get("top", [])
    if not top:
        print("\n  No expansion signals found this run.")
        if result.get("errors"):
            print(f"  ({len(result['errors'])} research errors — likely free-tier throttling)")
        return 0

    for i, row in enumerate(top, 1):
        sev = (row.get("severity") or "low").upper()
        conf = row.get("confidence", 0.0)
        ev = row.get("evidence") or []
        url = ev[0].get("source_url") if ev else ""
        print(f"\n  {i}. {row['name']}  [{sev}]  ·  {row['signal_type']}  ·  conf {conf:.0%}")
        print(f"     Signal:   {row.get('summary','')}")
        if url:
            print(f"     Evidence: {url}")
        draft = (row.get("draft") or "").strip().replace("\n", "\n               ")
        print(f"     Outreach: {draft}")

    print("\n" + _hr())
    delivery = result["delivery"]
    if delivery.get("mode") == "formatted":
        print("  ℹ️  Slack not configured — formatted blocks above. Set SLACK_WEBHOOK_URL "
              "or Composio env to post for real.")
    else:
        print(f"  ✅ Delivered {delivery.get('delivered')} message(s) to Slack "
              f"({delivery.get('mode')}, {delivery.get('channel')}).")
    if result.get("errors"):
        print(f"  ⚠️  {len(result['errors'])} customer(s) errored (throttling/no data).")
    print(_hr() + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
