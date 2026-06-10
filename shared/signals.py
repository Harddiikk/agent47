"""Signal data layer for the Intelligence sub-agent.

Minimal in-memory signal store with a Pydantic Signal model and a few seed
samples. Real signal sources (Slack, email, usage telemetry, etc.) land in
Part 5 via MCP.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator

SignalType = Literal["expansion", "risk", "health", "neutral"]
SignalSeverity = Literal["low", "medium", "high"]


class Signal(BaseModel):
    """A single observation about a client that the Intelligence agent reasons over."""

    client: str = Field(..., min_length=1, description="Short client identifier, e.g. 'acme'.")
    type: SignalType = Field(..., description="What kind of signal this is.")
    severity: SignalSeverity = Field(..., description="How urgent it is.")
    source: str = Field(..., min_length=1, description="Where the signal came from, e.g. 'slack', 'email', 'usage'.")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    text: str = Field(..., min_length=1, description="Human-readable description of the signal.")

    @field_validator("client", "source", "text")
    @classmethod
    def _strip_nonempty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must be non-empty")
        return v


# Seed sample signals — enough variety for the agent to demo classification.
SAMPLE_SIGNALS: list[Signal] = [
    Signal(
        client="acme",
        type="expansion",
        severity="medium",
        source="email",
        text="Founder of Acme asked if we can also automate their billing reconciliation.",
    ),
    Signal(
        client="acme",
        type="health",
        severity="low",
        source="usage",
        text="Weekly active usage of delivered support-deck workflow up 18% week-over-week.",
    ),
    Signal(
        client="globex",
        type="risk",
        severity="high",
        source="slack",
        text="Globex POC silent for 9 days; last message was a complaint about response latency.",
    ),
    Signal(
        client="initech",
        type="risk",
        severity="medium",
        source="email",
        text="Initech CFO questioned the price of the renewal in last week's call.",
    ),
    Signal(
        client="hooli",
        type="neutral",
        severity="low",
        source="slack",
        text="Hooli ops lead asked a documentation question; no action needed beyond reply.",
    ),
]


# Simple module-level store. Tests rely on this being a list copy.
_STORE: list[Signal] = list(SAMPLE_SIGNALS)


def all_signals() -> list[Signal]:
    """Return a copy of every signal currently in the store."""
    return list(_STORE)


def signals_for_client(client: str) -> list[Signal]:
    """Return all signals for a given client (case-insensitive match)."""
    needle = client.strip().lower()
    return [s for s in _STORE if s.client.lower() == needle]


def signals_by_severity(severity: SignalSeverity) -> list[Signal]:
    """Return all signals at the given severity."""
    return [s for s in _STORE if s.severity == severity]


def signals_by_type(signal_type: SignalType) -> list[Signal]:
    """Return all signals of the given type."""
    return [s for s in _STORE if s.type == signal_type]


def add_signal(signal: Signal) -> Signal:
    """Append a signal to the store and return it."""
    _STORE.append(signal)
    return signal


def reset_store() -> None:
    """Reset the store back to SAMPLE_SIGNALS. For tests."""
    _STORE.clear()
    _STORE.extend(SAMPLE_SIGNALS)
