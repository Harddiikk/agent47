"""Smoke test — verifies Agent 47 loads correctly."""

from shared.config import DEFAULT_MODEL


def test_agent47_loads():
    from agents.sdr_agent import agent47
    assert agent47.name == "sdr_agent"
    assert agent47.model == DEFAULT_MODEL
    assert "coordinator" in agent47.instruction
