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
    from agents.sdr_agent import agent47

    # single-agent design: root owns onboarding tools directly
    names = {getattr(t, "__name__", "") for t in agent47.tools}
    assert {"set_offers", "import_leads"} <= names


def test_root_agent_is_agent47():
    from agents.sdr_agent import root_agent, agent47

    assert root_agent is agent47


def test_onboarding_has_setup_tools():
    from agents.onboarding import onboarding

    names = {getattr(t, "__name__", "") for t in onboarding.tools}
    assert {"set_offers", "list_offers", "import_leads"} <= names


def test_root_agent_renamed_sdr_agent():
    from agents.sdr_agent import agent47, sdr_agent

    assert sdr_agent.name == "sdr_agent"
    assert agent47 is sdr_agent            # backward-compat alias
    assert "SDR Agent" in sdr_agent.instruction


def test_onboarding_prompt_supports_pdf_discovery():
    from agents.onboarding import onboarding

    text = onboarding.instruction.lower()
    assert "pdf" in text
    assert "set_offers" in text
