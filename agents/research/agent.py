"""Research — the SDR research specialist. Scans leads, reports findings, nothing else."""

from pathlib import Path
from google.adk import Agent
from orchestrator.tools import scan_leads, scan_my_book
from shared.attachment_guard import strip_unsupported_attachments
from shared.config import DEFAULT_MODEL

PROMPT_PATH = Path(__file__).parent.parent.parent / "shared" / "prompts" / "research_system.md"
SYSTEM_PROMPT = PROMPT_PATH.read_text()

research = Agent(
    name="research",
    model=DEFAULT_MODEL,
    instruction=SYSTEM_PROMPT,
    tools=[scan_leads, scan_my_book],
    before_model_callback=strip_unsupported_attachments,
)

root_agent = research
