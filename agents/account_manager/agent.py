"""Account Manager — sub-agent for ongoing client relationship management."""

from pathlib import Path
from google.adk import Agent
from shared.config import DEFAULT_MODEL

PROMPT_PATH = Path(__file__).parent.parent.parent / "shared" / "prompts" / "account_manager_system.md"
SYSTEM_PROMPT = PROMPT_PATH.read_text()

# Generic account manager (used when no specific client is named)
account_manager = Agent(
    name="account_manager",
    model=DEFAULT_MODEL,
    instruction=SYSTEM_PROMPT,
)


def make_client_agent(client_name: str, client_context: str) -> Agent:
    """Return a per-client account manager configured with the client's context.

    Args:
        client_name: Short identifier for the client (e.g., 'acme', 'globex').
            Will be slugified into the agent name.
        client_context: Free-form markdown describing the client — industry,
            scope of work, key contacts, current state. Becomes part of the
            agent's instruction.

    Returns:
        A configured google.adk.Agent dedicated to this client.
    """
    slug = "".join(c.lower() if c.isalnum() else "_" for c in client_name).strip("_")
    if not slug:
        raise ValueError("client_name must contain at least one alphanumeric character")

    instruction = (
        SYSTEM_PROMPT
        + "\n\n## CLIENT CONTEXT\n\n"
        + f"Client: {client_name}\n\n"
        + client_context.strip()
        + "\n"
    )

    return Agent(
        name=f"account_manager_{slug}",
        model=DEFAULT_MODEL,
        instruction=instruction,
    )


root_agent = account_manager
