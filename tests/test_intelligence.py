"""Tests for Part 4 — Intelligence sub-agent and signal data layer."""

import re

import pytest
from pydantic import ValidationError

from shared.config import DEFAULT_MODEL


# --- Intelligence agent tests ---


def test_intelligence_loads():
    from agents.intelligence import intelligence

    assert intelligence.name == "intelligence"
    assert intelligence.model == DEFAULT_MODEL
    assert intelligence.instruction and len(intelligence.instruction) > 0


def test_intelligence_prompt_has_taxonomy():
    from agents.intelligence import intelligence

    prompt = intelligence.instruction.lower()
    for term in ("expansion", "risk", "health", "neutral"):
        assert term in prompt, f"Missing taxonomy term: {term}"


def test_intelligence_prompt_severity_scale():
    from agents.intelligence import intelligence

    prompt = intelligence.instruction.lower()
    for level in ("low", "medium", "high"):
        assert re.search(rf"\b{level}\b", prompt), f"Missing severity: {level}"


def test_intelligence_no_external_comms():
    from agents.intelligence import intelligence

    prompt = intelligence.instruction.lower()
    assert "do not contact clients directly" in prompt


def test_intelligence_prompt_top_of_inbox():
    from agents.intelligence import intelligence

    assert re.search(r"top of inbox", intelligence.instruction, re.IGNORECASE)


# --- Intelligence tools (signal data layer wiring) ---


def test_intelligence_has_signal_tools():
    from agents.intelligence import intelligence

    assert intelligence.tools, "Intelligence agent should expose signal tools"


def test_intelligence_tools_return_json_serializable():
    import json

    from agents.intelligence.agent import (
        get_all_signals,
        get_signals_by_severity,
        get_signals_by_type,
        get_signals_for_client,
    )
    from shared.signals import reset_store

    reset_store()

    everything = get_all_signals()
    assert everything["signals"], "expected seed signals"
    json.dumps(everything)  # raises TypeError if not serializable

    assert get_signals_for_client("ACME")["signals"], "case-insensitive client lookup"
    assert get_signals_by_severity("high")["signals"]
    assert get_signals_by_type("expansion")["signals"]


def test_intelligence_tools_reject_bad_args():
    from agents.intelligence.agent import get_signals_by_severity, get_signals_by_type

    assert "error" in get_signals_by_severity("critical")
    assert "error" in get_signals_by_type("garbage")


# --- Agent 47 integration ---


def test_agent47_has_three_subagents():
    from agents.sdr_agent import agent47

    names = {a.name for a in agent47.sub_agents}
    assert names == {"onboarding", "account_manager", "intelligence", "execution"}


# --- Signal model tests ---


def test_signal_model_basic():
    from shared.signals import Signal

    s = Signal(client="acme", type="expansion", severity="high", source="email", text="hello")
    assert s.client == "acme"
    assert s.type == "expansion"
    assert s.severity == "high"
    assert s.source == "email"
    assert s.text == "hello"
    assert s.timestamp.tzinfo is not None


def test_signal_model_rejects_invalid_type():
    from shared.signals import Signal

    with pytest.raises(ValidationError):
        Signal(client="x", type="garbage", severity="low", source="s", text="t")


def test_signal_model_rejects_invalid_severity():
    from shared.signals import Signal

    with pytest.raises(ValidationError):
        Signal(client="x", type="risk", severity="critical", source="s", text="t")


def test_signal_model_rejects_blank_client():
    from shared.signals import Signal

    with pytest.raises(ValidationError):
        Signal(client="   ", type="risk", severity="low", source="s", text="t")


# --- Sample signals and store helpers ---


def test_sample_signals_minimum():
    from shared.signals import SAMPLE_SIGNALS

    assert len(SAMPLE_SIGNALS) >= 5
    types = {s.type for s in SAMPLE_SIGNALS}
    assert "expansion" in types
    assert "risk" in types


def test_signals_for_client_case_insensitive():
    from shared.signals import reset_store, signals_for_client

    reset_store()
    lower = signals_for_client("acme")
    upper = signals_for_client("ACME")
    assert len(lower) == len(upper)
    assert len(lower) >= 1


def test_signals_by_severity():
    from shared.signals import all_signals, reset_store, signals_by_severity

    reset_store()
    total = len(all_signals())
    counted = sum(len(signals_by_severity(s)) for s in ["low", "medium", "high"])
    assert counted == total


def test_signals_by_type():
    from shared.signals import all_signals, reset_store, signals_by_type

    reset_store()
    total = len(all_signals())
    counted = sum(len(signals_by_type(t)) for t in ["expansion", "risk", "health", "neutral"])
    assert counted == total


def test_add_signal_and_reset():
    from shared.signals import Signal, add_signal, all_signals, reset_store

    reset_store()
    base = len(all_signals())
    s = Signal(client="zog", type="neutral", severity="low", source="test", text="hi")
    add_signal(s)
    assert len(all_signals()) == base + 1
    reset_store()
    assert len(all_signals()) == base


# --- Regression: Parts 1-3 still work ---


def test_part1_2_3_unbroken():
    from agents.account_manager import account_manager, make_client_agent
    from agents.sdr_agent import agent47
    from agents.onboarding import onboarding  # noqa: F401

    assert {a.name for a in agent47.sub_agents} >= {"onboarding", "account_manager"}
    assert make_client_agent("Acme", "x").name == "account_manager_acme"
