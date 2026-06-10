"""Agent 47 — the root orchestrator agent."""

from pathlib import Path
from google.adk import Agent
from agents.onboarding import onboarding
from agents.account_manager import account_manager
from agents.intelligence import intelligence
from agents.execution import execution
from orchestrator.tools import MANAGER_TOOLS
from shared.config import DEFAULT_MODEL

# Load system prompt from markdown
PROMPT_PATH = Path(__file__).parent.parent.parent / "shared" / "prompts" / "agent47_system.md"
SYSTEM_PROMPT = PROMPT_PATH.read_text()

agent47 = Agent(
    name="agent47",
    model=DEFAULT_MODEL,
    instruction=SYSTEM_PROMPT,
    sub_agents=[onboarding, account_manager, intelligence, execution],
    tools=MANAGER_TOOLS,
)

# ADK convention: expose root agent so `adk run` and `adk web` can discover it
root_agent = agent47
