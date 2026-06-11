"""SDR Agent — the root orchestrator the founder talks to (brand: Agent 47)."""

from pathlib import Path
from google.adk import Agent
from agents.onboarding import onboarding
from agents.account_manager import account_manager
from agents.intelligence import intelligence
from agents.execution import execution
from orchestrator.tools import MANAGER_TOOLS
from shared.attachment_guard import strip_unsupported_attachments
from shared.config import DEFAULT_MODEL

# Load system prompt from markdown
PROMPT_PATH = Path(__file__).parent.parent.parent / "shared" / "prompts" / "sdr_agent_system.md"
SYSTEM_PROMPT = PROMPT_PATH.read_text()

sdr_agent = Agent(
    name="sdr_agent",
    model=DEFAULT_MODEL,
    instruction=SYSTEM_PROMPT,
    sub_agents=[onboarding, account_manager, intelligence, execution],
    tools=MANAGER_TOOLS,
    before_model_callback=strip_unsupported_attachments,
)

# Backward-compatible alias (the product brand is Agent 47; the bot persona is SDR Agent).
agent47 = sdr_agent

# ADK convention: expose root agent so `adk run` and `adk web` can discover it
root_agent = sdr_agent
