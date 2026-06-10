"""Headless SDR scan runner.  Run: python -m scripts.sdr_scan [csv]  (or `make sdr-scan`)."""
from __future__ import annotations

import os
import sys


def main() -> int:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:  # noqa: BLE001
        pass
    if not os.getenv("GEMINI_API_KEY"):
        print("⚠️  GEMINI_API_KEY is not set.")
        return 2
    csv_path = sys.argv[1] if len(sys.argv) > 1 else "data/leads.csv"

    from sdr.pipeline import run_scan

    print(f"\n🕴️  Agent 47 SDR — scanning {csv_path} …\n")
    r = run_scan(csv_path)
    print("═" * 78)
    print(f"  Batch #{r['batch_id']} · {r['total']} leads · {r['resolved']} resolved · "
          f"{r['unresolved']} unresolved · {r['signals_found']} signals · "
          f"delivery: {r['delivery'].get('mode')}")
    print("═" * 78)
    for i, t in enumerate(r["top"], 1):
        print(f"\n  {i}. {t['name']}  [{t['tier'].upper()} · {t['severity'].upper()} · "
              f"score {t['score']:.1f}]")
        print(f"     Signal:  {t['summary']}")
        print(f"     Offer:   {t['offer']}")
        if t["evidence_url"]:
            print(f"     Source:  {t['evidence_url']}")
    if not r["top"]:
        print("\n  No new signals this run (rescans only surface changes).")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
