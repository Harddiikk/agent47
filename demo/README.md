# Demo kit

Everything needed to run the full onboarding → scan demo at https://agent47.tech.

| File | Use it when |
|---|---|
| `brochure.pdf` | Onboarding asks what you sell → **upload this PDF**. The agent reads it and proposes the offer catalog (6 services with pricing) |
| `leads.xlsx` | Onboarding asks for your leads → **drop this Excel file**. Real, googleable businesses with proper websites, CRM-style headers (First name / Company / Website / …) that exercise the smart header mapping |

## The demo flow (3 minutes)

1. New session → *"I want to set this up for my business"*
2. When asked what you sell → upload `brochure.pdf` → confirm the extracted catalog
3. When asked for leads → drop `leads.xlsx` → "8 leads imported"
4. *"Scan my leads"* → watch Slack: live progress, then ranked verified cards
5. *"Give me the weekly intelligence brief"* → ranked priorities from the real scan ledger

## Before recording

- Clear the Slack channel (#all-agent-47)
- Reset the server's lead book/ledger for a fresh run:
  `ssh root@168.144.93.191 'docker exec agent47-web sh -c "rm -f data/sdr.db data/leads.csv data/.imported_files.json"'`
- Start a brand-new chat session
