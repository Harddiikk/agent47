"""SDR Agent — the single agent the founder talks to. Does everything itself.

Multi-agent transfers were tried and reverted: prompt-swapping on every handoff
broke context caching (latency) and made the founder experience bureaucratic.
One agent, all tools, act-first. The specialist apps still exist standalone
(onboarding, research, etc.) for direct use in the dev UI.
"""

from pathlib import Path
from google.adk import Agent
from agents.intelligence.agent import INTELLIGENCE_TOOLS
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
    tools=[*MANAGER_TOOLS, *INTELLIGENCE_TOOLS],
    before_model_callback=strip_unsupported_attachments,
)

# Backward-compatible alias (the product brand is Agent 47; the bot persona is SDR Agent).
agent47 = sdr_agent

# ADK convention: expose root agent so `adk run` and `adk web` can discover it
root_agent = sdr_agent
