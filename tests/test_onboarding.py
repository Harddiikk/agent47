"""Tests for the Onboarding Specialist sub-agent."""

from shared.config import DEFAULT_MODEL


def test_onboarding_loads():
    from agents.onboarding import onboarding

    assert onboarding.name == "onboarding"
    assert onboarding.model == DEFAULT_MODEL
    assert onboarding.instruction


def test_onboarding_prompt_has_phases():
    from agents.onboarding import onboarding

    text = onboarding.instruction.lower()
    assert "discovery" in text
    assert "scoping" in text
    assert "kickoff" in text


def test_onboarding_no_external_comms_clause():
    from agents.onboarding import onboarding

    assert "do not contact prospects or clients directly" in onboarding.instruction.lower()


def test_agent47_has_onboarding_subagent():
    from agents.agent47 import agent47

    assert any(a.name == "onboarding" for a in agent47.sub_agents)


def test_root_agent_is_agent47():
    from agents.agent47 import root_agent, agent47

    assert root_agent is agent47
