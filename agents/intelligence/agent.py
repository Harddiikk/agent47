"""Intelligence — sub-agent for client signal monitoring and recommendations."""

from pathlib import Path
from google.adk import Agent
from shared.config import DEFAULT_MODEL
from shared import signals

PROMPT_PATH = Path(__file__).parent.parent.parent / "shared" / "prompts" / "intelligence_system.md"
SYSTEM_PROMPT = PROMPT_PATH.read_text()


# --- Tools: expose the signal data layer to the agent ---
#
# ADK builds tool schemas from these signatures and docstrings, and serializes
# the return value as the tool result. shared.signals returns Signal objects,
# which aren't JSON-serializable, so each wrapper dumps them to plain dicts.


def get_all_signals() -> dict:
    """Return every client signal currently in the store.

    Use this to build a weekly Intelligence Brief or get a full picture of the
    book before classifying or ranking.
    """
    return {"signals": [s.model_dump(mode="json") for s in signals.all_signals()]}


def get_signals_for_client(client: str) -> dict:
    """Return all signals for a single client (case-insensitive).

    Args:
        client: Short client identifier, e.g. 'acme', 'globex'.
    """
    found = signals.signals_for_client(client)
    return {"client": client, "signals": [s.model_dump(mode="json") for s in found]}


def get_signals_by_severity(severity: str) -> dict:
    """Return all signals at a given severity level.

    Args:
        severity: One of 'low', 'medium', or 'high'.
    """
    if severity not in ("low", "medium", "high"):
        return {"error": f"invalid severity '{severity}'; expected low, medium, or high"}
    found = signals.signals_by_severity(severity)  # type: ignore[arg-type]
    return {"severity": severity, "signals": [s.model_dump(mode="json") for s in found]}


def get_signals_by_type(signal_type: str) -> dict:
    """Return all signals of a given type.

    Args:
        signal_type: One of 'expansion', 'risk', 'health', or 'neutral'.
    """
    if signal_type not in ("expansion", "risk", "health", "neutral"):
        return {"error": f"invalid type '{signal_type}'; expected expansion, risk, health, or neutral"}
    found = signals.signals_by_type(signal_type)  # type: ignore[arg-type]
    return {"type": signal_type, "signals": [s.model_dump(mode="json") for s in found]}


INTELLIGENCE_TOOLS = [
    get_all_signals,
    get_signals_for_client,
    get_signals_by_severity,
    get_signals_by_type,
]

from shared.attachment_guard import strip_unsupported_attachments

intelligence = Agent(
    name="intelligence",
    model=DEFAULT_MODEL,
    instruction=SYSTEM_PROMPT,
    tools=INTELLIGENCE_TOOLS,
    before_model_callback=strip_unsupported_attachments,
)

root_agent = intelligence
