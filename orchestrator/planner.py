"""Planner — produces an implementation plan as TEXT via the Gemini API.

Why a direct API call instead of a Gemini CLI worker: the CLI is aggressively
tool-eager (it attempts file writes / shell even when told not to), and the only
policy rule proven to hard-stop it is a blanket `deny "*"`, which then makes the
run error out instead of returning text. A plain `generate_content` call has NO
tools at all, so the planning pass *cannot* touch disk, shell, or network — it
can only think and emit the plan. That is the safety boundary the approval gate
needs. Real building (with shell/disk) happens later via GeminiWorker, only
after the founder approves.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from shared.config import DEFAULT_MODEL

# Substrings that mark a transient, worth-retrying Gemini error (free-tier spikes).
_TRANSIENT = ("503", "unavailable", "resource_exhausted", "overloaded", "high demand")


def _is_transient(err: str) -> bool:
    e = err.lower()
    return any(t in e for t in _TRANSIENT)

_SYSTEM = (
    "You are a senior solutions architect for an AI automation agency. "
    "Given a client's context and a task, produce a clear, concrete implementation "
    "plan and architecture: the approach, the components/files involved, key "
    "decisions and trade-offs, and an ordered list of build steps. Be specific and "
    "buildable. This is a PLAN ONLY — do not write code. Output plain markdown."
)


@dataclass
class PlanResult:
    success: bool
    text: str
    model: str
    error: str = ""


class GeminiPlanner:
    """Generates plan text via google-genai. Tool-free, so it cannot take actions."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        client=None,
        *,
        max_retries: int = 3,
        backoff: float = 2.0,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.model = model
        self._client = client  # injectable; created lazily so import needs no API key
        self.max_retries = max_retries
        self.backoff = backoff
        self._sleep = sleep

    def _get_client(self):
        if self._client is None:
            from google import genai

            self._client = genai.Client()
        return self._client

    def plan(self, context: str, task: str) -> PlanResult:
        prompt = self.compose(context, task)
        last_error = ""
        for attempt in range(self.max_retries + 1):
            try:
                resp = self._get_client().models.generate_content(
                    model=self.model, contents=prompt
                )
                text = (getattr(resp, "text", None) or "").strip()
                if text:
                    return PlanResult(True, text, self.model)
                last_error = "empty response (model throttled)"
            except Exception as e:  # noqa: BLE001 — surface API errors as data, not crashes
                last_error = f"{type(e).__name__}: {e}"
                if not _is_transient(last_error):
                    break  # non-transient (bad request, auth, etc.) — don't retry
            if attempt < self.max_retries:
                self._sleep(self.backoff * (2**attempt))
        return PlanResult(False, "", self.model, last_error)

    @staticmethod
    def compose(context: str, task: str) -> str:
        parts = [_SYSTEM]
        if (context or "").strip():
            parts.append("## Client context\n\n" + context.strip())
        parts.append("## Task\n\n" + (task or "").strip())
        return "\n\n".join(parts)
