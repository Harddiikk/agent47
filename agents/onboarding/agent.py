"""Onboarding Specialist — takes a new founder from hello to first scan."""

from pathlib import Path
from google.adk import Agent
from shared.config import DEFAULT_MODEL

# Load system prompt from markdown
PROMPT_PATH = Path(__file__).parent.parent.parent / "shared" / "prompts" / "onboarding_system.md"
SYSTEM_PROMPT = PROMPT_PATH.read_text()

from orchestrator.tools import import_leads, list_offers, scan_leads, set_offers
from shared.attachment_guard import strip_unsupported_attachments

# scan_leads included so onboarding can launch the founder's FIRST scan itself
# (kickoff phase). Without it, the standalone app dead-ends after importing.
onboarding = Agent(
    name="onboarding",
    model=DEFAULT_MODEL,
    instruction=SYSTEM_PROMPT,
    tools=[set_offers, list_offers, import_leads, scan_leads],
    before_model_callback=strip_unsupported_attachments,
)

# ADK convention: expose root agent
root_agent = onboarding
