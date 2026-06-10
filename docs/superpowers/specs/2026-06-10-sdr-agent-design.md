# SDR Research Agent — Design Spec

**Date:** 2026-06-10 · **Status:** awaiting user approval · **Project:** Agent 47 (repo `Mou`)

## 1. Goal

Turn Agent 47's existing `scan_my_book` pipeline into a real SDR (Sales Development Rep)
research engine: upload a CSV of existing/past leads → the system enriches each lead with
**verified, correctly-matched** new data points → detects what *changed* since the last scan
→ matches each signal to a sellable service offer → delivers **well-structured, managed**
opportunity cards to Slack for a human to approve and act on.

Revenue thesis: database reactivation — existing leads cost $0 to acquire and convert 2–5×
better than cold outreach. The product is the *signal → offer match + speed*, not the data.

## 2. Explicit defaults (user to confirm)

These two inputs were not yet provided; the design proceeds on defaults that are config, not
code, so changing them later is trivial:

- **D1 — Offer catalog** (seeded from user's own words: "Google Maps services, SEO service,
  and whatever we can offer"): GBP/Maps setup & ranking · Local SEO · Google Ads management ·
  Reputation management · Service landing pages · AI receptionist / workflow automation.
  Stored in `data/offers.yaml`-style config (actual format JSON to avoid a new dependency).
- **D2 — Volume & cadence:** ≤ 500 leads per book, weekly rescan, `max_workers=4`. Grounded
  search calls are tiered (see §5) to keep cost sane at this volume.

## 3. Scope

**Phase 1 (this spec, buildable now):**
- New **`sdr/` package** — strictly additive. The frozen hackathon pipeline
  (`shared/research.py`, `shared/book.py`, `shared/outreach.py`, `scan_my_book`) is untouched
  and stays demo-ready. Shared logic is *imported from* those modules, never modified in them.
- Lead ingestion from CSV (richer schema), batch jobs with Slack status posts.
- Entity resolution gate, trust-tiered enrichment, verification, delta ledger, offer
  matching, Block Kit Slack cards.
- CLI runner (`make sdr-scan`) + one new manager tool for Agent 47 (`scan_leads()`).

**Phase 2 (designed for, not built now):**
- CSV-upload-to-Slack as the ingestion trigger (Socket Mode; the user's Slack app exists).
- Interactive card buttons: Approve & Send (via Composio email) / Edit / Dismiss.
- Google Places API collector (needs a `GOOGLE_PLACES_API_KEY`).

**Non-goals:** a CRM; auto-sending without approval; direct LinkedIn scraping (ToS — LinkedIn
data only via grounded search `site:linkedin.com` queries); multi-vertical configs beyond one
seed vertical (dental/medspa); touching the orchestrator (plan/approve/build) layer.

## 4. Lead schema (CSV in, SQLite after)

CSV columns: `name, domain, linkedin_url, location, services, contact_name, contact_email,
last_service, deal_value, status`. Only `name` is required; everything else improves entity
resolution and offer matching. Loader is tolerant: unknown columns ignored, missing optional
columns default to empty.

New SQLite file `data/sdr.db` (stdlib sqlite3, same style as `orchestrator/store.py`):

- `leads` — one row per lead; identity fields + resolution score + timestamps.
- `data_points` — append-only ledger: `(lead_id, field, value, source, confidence_tier,
  evidence_url, seen_at)`. "New data point" ≡ a row whose `(field, value)` differs from the
  lead's latest prior row for that field. This table IS the delta-detection mechanism.
- `signals` — derived opportunities: `(lead_id, signal_type, summary, tier, matched_offer,
  score, posted_at, state)` with state ∈ `new → posted → approved → sent → dismissed`.
  Uniqueness on `(lead_id, signal_type, summary-hash)` prevents reposting the same signal.
- `batches` — one row per upload/scan run: counts, started/finished, for status reporting.

## 5. Pipeline (per batch)

```
ingest CSV → batches row + Slack "scan started" post
  → ENTITY RESOLUTION (per lead)
  → ENRICH  (collectors, trust-tiered)
  → VERIFY  (tier rules below) → data_points rows
  → DELTA   (vs ledger) → new/changed points only
  → SIGNAL + OFFER MATCH (rules table from offer catalog)
  → SCORE   (severity × confidence × deal_value-if-known)
  → DELIVER (Slack digest + ranked Block Kit cards, drafts in threads)
```

**Entity resolution (the correctness gate).** Before any signal hunting: fetch the lead's
`domain` homepage; confirm name/location appear (fuzzy match). Grounded-search findings must
reference the same domain or location to attach. Result: `resolution ∈ {verified, weak,
unresolved}`. `unresolved` leads are enriched but **never pitched** and are flagged in the
digest ("3 leads need a domain check").

**Collectors, in trust order:**
1. **Website snapshot + diff** (stdlib fetch of homepage + up to 3 likely pages — /locations,
   /services, /blog—first scan stores a text snapshot in `data_points`; rescans diff against
   it). A diff is deterministic ⇒ tier ✅.
2. **Grounded Gemini search** (reuses `shared/research.py`'s verified grounding pattern,
   extended prompt asking for the vertical checklist fields). Tier ⚠️ unless corroborated.
3. **(Phase 2) Google Places API** — reviews/rating/locations. Deterministic ⇒ tier ✅.

**Verification rules:**
- Tier ✅ *verified*: deterministic source (website diff / Places), OR grounded claim
  corroborated by a fetch of the cited URL containing the claim's key terms, with a parseable
  date ≤ 12 months old.
- Tier ⚠️ *probable*: single grounded source, evidence URL fetchable, no corroboration.
- Below that: stored in the ledger, never posted.

**Offer matching.** A small rules table maps `signal_type/field` → offer from the catalog
(new location → GBP + local SEO; new service/equipment → landing page + ads; review rating
< 4.0 or falling → reputation mgmt; hiring admin/front-desk → AI receptionist; no online
booking detected → booking automation). One best offer per signal, named on the card.

## 6. Slack delivery (well-structured & managed)

Existing webhook, upgraded payloads from plain `text` to **Block Kit `blocks`**:

- **Digest message** opens every batch: `Scan #N · X leads · Y signals (Z verified) · top 3`.
- **One card per signal**, posted in ranked order (verified-high first): header with name +
  tier badge + severity; fields for signal summary, evidence link, matched offer, contact;
  the **drafted outreach goes in the card's thread** (webhook limitation: webhooks can't
  thread — Phase 1 compromise: draft included as a collapsed-style trailing section block;
  true threading arrives with the bot token in Phase 2).
- **No repeats:** the `signals` table's uniqueness rule means a rescan only posts new deltas.
- Drafting reuses `draft_outreach`'s pattern with the matched offer woven in ("…that's
  exactly what our local-SEO package handles for new locations…").

## 7. Components (all new files, plus one additive edit to `orchestrator/tools.py`)

| File | Responsibility |
|---|---|
| `sdr/store.py` | `SdrStore` — leads / data_points / signals / batches tables |
| `sdr/ingest.py` | CSV loader (rich schema) + batch creation |
| `sdr/resolve.py` | entity resolution gate |
| `sdr/collect.py` | website snapshot/diff collector + grounded-search collector (imports from `shared/research.py`) |
| `sdr/verify.py` | tier rules: corroboration fetch, recency parse |
| `sdr/offers.py` | offer catalog (config) + signal→offer matcher |
| `sdr/pipeline.py` | orchestrates §5; concurrent over leads (`max_workers=4`) |
| `sdr/slack.py` | Block Kit digest + cards via existing webhook |
| `scripts/sdr_scan.py` | CLI runner (`make sdr-scan FILE=...`) |
| `orchestrator/tools.py` | +1 additive tool `scan_leads(csv_path)` in `MANAGER_TOOLS` |
| `data/offers.json` | default offer catalog (D1) |

## 8. Error handling

Same doctrine as the existing codebase, now load-bearing: every collector/verifier returns
data or an error field — never raises into the pipeline; per-lead failure never sinks a
batch; Gemini calls retry with backoff on transient errors (reuse existing `_is_transient`
pattern); Slack delivery degrades webhook → formatted text; batch always finishes and always
posts a final digest, including error counts.

## 9. Testing

All offline with fakes/fixtures, matching house style: store round-trips & delta queries;
resolver against canned HTML; collectors with fake fetchers/clients; verifier tier decisions
(corroborated vs not, stale vs fresh); offer matcher rules; pipeline end-to-end with all
fakes; Block Kit payload shape. Existing 101 tests must keep passing untouched. One opt-in
live smoke (`RUN_SDR_SMOKE=1`) for a 2-lead real scan.

## 10. Risks

- **Wrong-business matching** is the product-killer → that's why resolution is a hard gate.
- **Cost/quota:** grounded search only runs for resolved leads, and rescans skip leads whose
  website diff is empty unless stale > 30 days (tiered spend).
- **Slack webhook can't thread/button** — accepted for Phase 1; the existing Slack app
  (Socket Mode already enabled) is the Phase 2 path.
- **Deadline:** hackathon build is frozen at the initial commit; this work happens on branch
  `sdr-agent`, so `main` stays submission-ready.
