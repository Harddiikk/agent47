# Agent 47

AI operations agent for AI automation agencies. Built for the Google for Startups AI Agents Challenge.

Domain: [agent47.tech](https://agent47.tech)

## What it does

Agent 47 turns a list of your **past customers** into warm pipeline. Tell it "scan my book"
and it will, for every customer:

1. **Research them live on the web** (Gemini + Google Search grounding) for real, recent
   growth signals — new locations, senior hires, funding, press.
2. **Rank** the hits by severity and confidence, with **verifiable source links**.
3. **Draft a personalized outreach** email referencing the specific signal.
4. **Post the opportunities to Slack** for you to action.

Everything runs on an all-Gemini stack via Google ADK, with the four specialist sub-agents
(Onboarding, Account Manager, Intelligence, Execution) behind a single agent you talk to.

## Quick start
1. `python3 -m venv .venv && source .venv/bin/activate`
2. `cp .env.example .env` and add your `GEMINI_API_KEY` from https://aistudio.google.com/apikey
3. `make install`
4. `make scan` — **headless demo:** scan `data/customers.csv` → research → draft → Slack/print
5. `make web` — chat with Agent 47 in the ADK web UI; say *"scan my book"*
6. `make run` — chat with Agent 47 in the terminal
7. `make test` — run the test suite (101 tests)

### The "scan my book" pipeline
- Customers live in `data/customers.csv` (`name, location, services, contact_email`).
- Live research uses Google Search **grounding** — source URLs come from the model's
  grounding metadata, not free text, so they're real.
- Found signals persist to `data/book.db` (SQLite).
- **Slack delivery** (optional, for a real post on camera): set `SLACK_WEBHOOK_URL` to a
  Slack Incoming Webhook, or configure Composio (below). Without either, the pipeline prints
  formatted Slack blocks so it always completes.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full flow and [DEVPOST.md](DEVPOST.md) for the
submission write-up.

## Stack
- Google ADK 2.0 (Python)
- Gemini 2.5 Flash / Pro / Live
- MCP for tool access (via Composio Tool Router)

## Architecture
Agent 47 is the root agent the founder talks to. It delegates to four specialists:
- **Onboarding** — discovery, scoping, kickoff for new clients
- **Account Manager** — ongoing client work, status tracking, issue triage
- **Intelligence** — signal monitoring across the client book, weekly briefs
- **Execution** — drafts and (with founder approval) sends comms via Gmail / Calendar / Slack / 500+ apps through Composio

## Composio setup (optional, for Execution)

The Execution sub-agent uses Composio's hosted MCP Tool Router for Gmail, Calendar, Slack, and 500+ other apps. Without it, Execution drafts only and asks you to send manually.

1. Sign up at https://dashboard.composio.dev and grab your API key from Settings → API Keys.
2. Add to `.env`:
   ```
   COMPOSIO_API_KEY=...
   COMPOSIO_USER_ID=your-email@example.com   # any stable identifier
   ```
3. Restart `make web`. Execution will now have tools attached. The first time you ask it to act, Composio will ask you to authorize each app via OAuth (one-time per app).
