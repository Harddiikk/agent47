"""Tests for the Execution sub-agent (Part 5). All run offline without API keys."""

import importlib
from pathlib import Path

from shared.config import DEFAULT_MODEL

ROOT = Path(__file__).parent.parent


def test_execution_loads_without_composio(monkeypatch):
    monkeypatch.delenv("COMPOSIO_API_KEY", raising=False)
    monkeypatch.delenv("COMPOSIO_USER_ID", raising=False)
    from agents.execution import agent as exec_mod
    importlib.reload(exec_mod)
    execution = exec_mod.execution
    assert execution.name == "execution"
    assert execution.model == DEFAULT_MODEL
    assert execution.instruction
    assert execution.tools == []


def test_build_composio_toolset_returns_none_without_env(monkeypatch):
    monkeypatch.delenv("COMPOSIO_API_KEY", raising=False)
    monkeypatch.delenv("COMPOSIO_USER_ID", raising=False)
    from agents.execution.agent import _build_composio_toolset
    assert _build_composio_toolset() is None


def test_execution_prompt_covers_capabilities():
    text = (ROOT / "shared" / "prompts" / "execution_system.md").read_text().lower()
    assert "gmail" in text or "email" in text
    assert "calendar" in text
    assert "slack" in text
    assert "composio" in text


def test_execution_prompt_requires_approval():
    text = (ROOT / "shared" / "prompts" / "execution_system.md").read_text().lower()
    assert "approval" in text or "approve" in text


def test_execution_prompt_no_send_without_approval():
    text = (ROOT / "shared" / "prompts" / "execution_system.md").read_text().lower()
    assert "never send without" in text


def test_execution_prompt_audit():
    text = (ROOT / "shared" / "prompts" / "execution_system.md").read_text().lower()
    assert "audit" in text or "running summary" in text


def test_agent47_has_four_subagents():
    from agents.sdr_agent import agent47
    names = {a.name for a in agent47.sub_agents}
    assert names == {"onboarding", "account_manager", "intelligence", "execution"}


def test_parts_1_through_4_unbroken():
    from agents.sdr_agent import agent47
    from agents.onboarding import onboarding
    from agents.account_manager import account_manager
    from agents.intelligence import intelligence
    from shared.signals import SAMPLE_SIGNALS
    assert agent47.name == "sdr_agent"
    assert len(agent47.sub_agents) == 4
    assert onboarding.name == "onboarding"
    assert account_manager.name == "account_manager"
    assert intelligence.name == "intelligence"
    assert len(SAMPLE_SIGNALS) >= 5


def test_env_example_has_composio_keys():
    text = (ROOT / ".env.example").read_text()
    assert "COMPOSIO_API_KEY" in text
    assert "COMPOSIO_USER_ID" in text


def test_requirements_has_mcp_and_composio():
    text = (ROOT / "requirements.txt").read_text().lower()
    assert "mcp" in text
    assert "composio" in text
    assert "composio_google" in text or "composio-google" in text


def test_readme_has_composio_section():
    text = (ROOT / "README.md").read_text().lower()
    assert "composio" in text
    assert "composio_api_key" in text
