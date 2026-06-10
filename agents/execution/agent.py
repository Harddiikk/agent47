"""Execution — sub-agent that drafts and (with approval) sends comms via Composio."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from google.adk import Agent
from shared.config import DEFAULT_MODEL

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).parent.parent.parent / "shared" / "prompts" / "execution_system.md"
SYSTEM_PROMPT = PROMPT_PATH.read_text()


def _build_composio_toolset():
    """Try to construct a Composio MCP toolset. Returns None on any failure.

    Failure modes that all return None (not raise):
      - COMPOSIO_API_KEY or COMPOSIO_USER_ID not set
      - composio / composio_google packages not installed
      - mcp package not installed
      - Network failure when creating the Composio session
      - Any other unexpected exception
    """
    api_key = os.getenv("COMPOSIO_API_KEY")
    user_id = os.getenv("COMPOSIO_USER_ID")
    if not api_key or not user_id:
        logger.info(
            "Composio env vars not set (COMPOSIO_API_KEY / COMPOSIO_USER_ID); "
            "Execution will load without external tools."
        )
        return None
    try:
        from composio import Composio
        from composio_google import GoogleProvider
        from google.adk.tools.mcp_tool.mcp_session_manager import (
            StreamableHTTPConnectionParams,
        )
        from google.adk.tools.mcp_tool.mcp_toolset import McpToolset

        client = Composio(api_key=api_key, provider=GoogleProvider())
        session = client.create(user_id=user_id, toolkits=["composio"])
        url = session.mcp.url
        return McpToolset(
            connection_params=StreamableHTTPConnectionParams(
                url=url,
                headers={"x-api-key": api_key},
            ),
        )
    except Exception as e:  # noqa: BLE001 — deliberate broad catch for graceful degradation
        logger.warning(
            "Composio toolset setup failed: %s. Execution will run without external tools.",
            e,
        )
        return None


_composio_toolset = _build_composio_toolset()
_tools = [_composio_toolset] if _composio_toolset is not None else []

execution = Agent(
    name="execution",
    model=DEFAULT_MODEL,
    instruction=SYSTEM_PROMPT,
    tools=_tools,
)

root_agent = execution
