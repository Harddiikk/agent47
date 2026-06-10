"""Tests for the Account Manager sub-agent and make_client_agent factory."""

import pytest
from agents.account_manager import account_manager, make_client_agent
from shared.config import DEFAULT_MODEL


def test_account_manager_loads():
    assert account_manager.name == "account_manager"
    assert account_manager.model == DEFAULT_MODEL
    assert account_manager.instruction
    assert len(account_manager.instruction) > 0


def test_account_manager_prompt_covers_areas():
    prompt = account_manager.instruction.lower()
    assert "status" in prompt
    assert "issue" in prompt
    assert "recommendation" in prompt  # covers 'recommendations' too
    assert "report" in prompt  # covers 'reporting' too


def test_account_manager_no_external_comms():
    assert "do not contact clients directly" in account_manager.instruction.lower()


def test_make_client_agent_basic():
    agent = make_client_agent("Acme Corp", "Test scope")
    assert agent.name == "account_manager_acme_corp"
    assert agent.model == DEFAULT_MODEL
    assert "Acme Corp" in agent.instruction
    assert "Test scope" in agent.instruction
    assert "CLIENT CONTEXT" in agent.instruction


def test_make_client_agent_slugifies():
    agent = make_client_agent("Globex 2.0!", "ctx")
    assert agent.name.startswith("account_manager_globex")
    assert "account_manager_globex" in agent.name


def test_make_client_agent_rejects_empty():
    with pytest.raises(ValueError):
        make_client_agent("!!!", "ctx")


def test_agent47_has_both_subagents():
    from agents.agent47 import agent47

    names = [a.name for a in agent47.sub_agents]
    assert "onboarding" in names
    assert "account_manager" in names


def test_part1_and_part2_unbroken():
    from agents.agent47 import agent47
    from agents.onboarding import onboarding

    assert agent47.name == "agent47"
    assert onboarding.name == "onboarding"
    names = [a.name for a in agent47.sub_agents]
    assert "onboarding" in names
