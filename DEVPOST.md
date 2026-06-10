# Agent 47 — Devpost Submission

> An AI operations agent that turns an agency's **past customers** into warm pipeline —
> by researching each one live on the web for growth signals, then drafting and delivering
> personalized outreach.

## The problem

Agencies sit on a goldmine they ignore: **past customers**. A former client who just opened
their 100th location, raised funding, or hired a VP of Ops is the single warmest lead you can
get — but nobody has time to manually Google every old account every week. The signal is
public; the labor isn't worth it. So the outreach never happens.

## The solution

Tell Agent 47 **"scan my book."** It runs a four-step pipeline over your entire customer list:

1. **Research** — for each customer, Gemini searches the live web (Google Search grounding)
   for real, recent growth signals: new locations, senior hires, funding, press.
2. **Rank** — keeps only genuine signals, ordered by severity × confidence, each with a
   **verifiable source link** (pulled from grounding metadata, not hallucinated).
3. **Draft** — writes a personalized outreach email referencing the specific milestone.
4. **Deliver** — posts the ranked opportunities + drafts to Slack to action.

In a live run over 8 seeded businesses it surfaced **7 real signals** — e.g. *"Milan Laser
opened its 400th clinic (Aug 2025) and appointed six new senior leaders (Nov 2025)"* and
*"L'Oréal acquired a 36% stake in SkinSpirit"* — each with a working source URL and a tailored
email, in one command.

## How it works

- **Google ADK 2.0** multi-agent system: one root agent (Agent 47) the founder talks to,
  delegating to four specialists (Onboarding, Account Manager, Intelligence, Execution).
- **Gemini 2.5 Flash + Google Search grounding** does the research. Critically, evidence URLs
  come from `response.grounding_metadata`, so they're **real and clickable** — the difference
  between a demo and a toy.
- **Concurrent scan** (`ThreadPoolExecutor`) with per-call exponential backoff to ride out
  free-tier throttling; every failure degrades to data, never a crash.
- **SQLite** persists found signals to a `book_signals` table.
- **Composio MCP Tool Router** for real Slack/Gmail delivery, with graceful fallback
  (Slack webhook → formatted blocks) so the pipeline always completes.
- Runs two ways: the **ADK web UI** ("scan my book") or a **headless CLI** (`make scan`) — the
  reliable demo path.

## Tech stack

`Google ADK 2.0` · `Gemini 2.5 Flash` · `Google Search grounding (google-genai)` ·
`Composio / MCP` · `SQLite` · `concurrent.futures` · `Python 3.12` · `pytest` (101 tests).

## How it maps to the rubric

| Criterion | How Agent 47 hits it |
|---|---|
| **Technical execution** | Real Google Search **grounding** with verifiable citations; concurrent research with retry/backoff; multi-agent ADK architecture; clean module boundaries; 101 passing tests; never-crash error handling. |
| **Business value** | Reactivates dormant customers — the highest-converting, lowest-cost pipeline an agency has. Turns hours of manual research into one command, weekly. |
| **Innovation** | Past-customer **reactivation via live grounded research**, not generic cold outreach. Signals are real, recent, and sourced — then auto-personalized and delivered. |
| **Demo quality** | One-command headless runner (`make scan`) prints a clean ranked table with real signals + drafts; ADK UI shows the agent reasoning. Always completes regardless of Slack/Composio config. |

## What's next

- Two-way: ingest replies and let the **Execution** agent send approved outreach via Composio.
- Scheduled weekly scans with a daily Slack digest (the autonomous-daemon roadmap).
- Expand signal types (job-posting velocity, tech-stack changes, review trends).
- CRM import for the customer book instead of a CSV.

## Run it

```bash
cp .env.example .env   # add GEMINI_API_KEY
make install
make scan              # headless end-to-end demo
# or: make web  → say "scan my book"
```
