"""Onboarding Specialist — sub-agent for new client onboarding."""

from pathlib import Path
from google.adk import Agent
from shared.config import DEFAULT_MODEL

# Load system prompt from markdown
PROMPT_PATH = Path(__file__).parent.parent.parent / "shared" / "prompts" / "onboarding_system.md"
SYSTEM_PROMPT = PROMPT_PATH.read_text()

from shared.attachment_guard import strip_unsupported_attachments

onboarding = Agent(
    name="onboarding",
    model=DEFAULT_MODEL,
    instruction=SYSTEM_PROMPT,
    before_model_callback=strip_unsupported_attachments,
)

# ADK convention: expose root agent
root_agent = onboarding
