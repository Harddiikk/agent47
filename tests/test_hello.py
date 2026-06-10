"""Smoke test — verifies Agent 47 loads correctly."""

from shared.config import DEFAULT_MODEL


def test_agent47_loads():
    from agents.agent47 import agent47
    assert agent47.name == "agent47"
    assert agent47.model == DEFAULT_MODEL
    assert "operations agent" in agent47.instruction
