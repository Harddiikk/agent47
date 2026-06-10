"""Orchestrator — the always-on layer that turns Agent 47 into a manager.

Components (built step by step):
  - worker.py   : GeminiWorker — launches headless `gemini` CLI runs (DONE, step 1)
  - approval    : Telegram/Slack approval gate (later)
  - daemon      : event loop (Composio triggers) + scheduler (later)
  - store       : persistent client/plan/session state (later)
"""
