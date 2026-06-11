"""The main agent does everything itself; specialists remain standalone apps."""


def _tool_names(agent):
    return {getattr(t, "__name__", "") for t in agent.tools}


def test_root_is_self_sufficient():
    """No transfers needed: the founder-facing agent owns the whole loop."""
    from agents.sdr_agent import sdr_agent

    names = _tool_names(sdr_agent)
    assert {"scan_leads", "scan_my_book", "import_leads", "set_offers",
            "list_offers", "add_client", "list_clients", "dispatch_plan",
            "get_all_signals", "get_signals_by_severity"} <= names
    # no sub-agent routing: transfers swap system prompts and broke caching/UX
    assert not sdr_agent.sub_agents


def test_root_greeting_leads_with_core_job_not_departments():
    from agents.sdr_agent import sdr_agent

    text = sdr_agent.instruction.lower()
    assert "never greet with a menu" in text
    assert "past customers" in text
    assert "scan my leads" in text
    assert "act first" in text


def test_specialist_apps_still_standalone():
    """The focused apps keep working for direct use in the dev UI."""
    from agents.account_manager import account_manager
    from agents.onboarding import onboarding
    from agents.research import research

    assert {"scan_leads", "scan_my_book"} <= _tool_names(research)
    assert {"set_offers", "list_offers", "import_leads"} <= _tool_names(onboarding)
    assert {"list_clients", "add_client"} <= _tool_names(account_manager)


def test_research_has_attachment_guard():
    from agents.research import research

    cb = research.before_model_callback
    cbs = cb if isinstance(cb, list) else [cb]
    assert any(getattr(c, "__name__", "") == "strip_unsupported_attachments"
               for c in cbs)


def test_every_app_can_scan_after_a_file_drop():
    """User rule: behavior parity across ALL apps; a lead file dropped in any
    app must be scannable right there, never a dead end."""
    from agents.account_manager import account_manager
    from agents.execution import execution
    from agents.intelligence import intelligence
    from agents.onboarding import onboarding
    from agents.research import research
    from agents.sdr_agent import sdr_agent

    for app in (sdr_agent, onboarding, research, account_manager,
                intelligence, execution):
        assert "scan_leads" in _tool_names(app), f"{app.name} cannot scan"
