"""Each agent owns its lane exclusively; the root only coordinates."""


def _tool_names(agent):
    return {getattr(t, "__name__", "") for t in agent.tools}


def test_root_is_pure_coordinator():
    from agents.sdr_agent import sdr_agent

    assert _tool_names(sdr_agent) == {"dispatch_plan", "list_plans", "get_plan"}
    assert "routing table" in sdr_agent.instruction.lower()


def test_research_owns_scans_exclusively():
    from agents.onboarding import onboarding
    from agents.research import research
    from agents.sdr_agent import sdr_agent

    assert _tool_names(research) == {"scan_leads", "scan_my_book"}
    for other in (sdr_agent, onboarding):
        assert not ({"scan_leads", "scan_my_book"} & _tool_names(other))


def test_onboarding_owns_setup_exclusively():
    from agents.onboarding import onboarding
    from agents.research import research
    from agents.sdr_agent import sdr_agent

    assert {"set_offers", "list_offers", "import_leads"} <= _tool_names(onboarding)
    for other in (sdr_agent, research):
        assert not ({"set_offers", "import_leads"} & _tool_names(other))


def test_account_manager_owns_clients():
    from agents.account_manager import account_manager
    from agents.sdr_agent import sdr_agent

    assert {"list_clients", "add_client"} <= _tool_names(account_manager)
    assert not ({"list_clients", "add_client"} & _tool_names(sdr_agent))


def test_research_has_attachment_guard():
    from agents.research import research

    cb = research.before_model_callback
    cbs = cb if isinstance(cb, list) else [cb]
    assert any(getattr(c, "__name__", "") == "strip_unsupported_attachments"
               for c in cbs)
