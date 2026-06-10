"""Tests for GeminiPlanner. The API call is mocked via an injected fake client."""
from orchestrator.planner import GeminiPlanner, PlanResult


class _FakeResp:
    def __init__(self, text):
        self.text = text


class _FakeModels:
    def __init__(self, text=None, raises=None, script=None):
        self._text = text
        self._raises = raises
        # script: list of ("text", value) | ("raise", exc) consumed per call
        self._script = list(script) if script else None
        self.calls = []

    def generate_content(self, *, model, contents):
        self.calls.append({"model": model, "contents": contents})
        if self._script is not None:
            kind, value = self._script.pop(0)
            if kind == "raise":
                raise value
            return _FakeResp(value)
        if self._raises:
            raise self._raises
        return _FakeResp(self._text)


class _FakeClient:
    def __init__(self, text=None, raises=None, script=None):
        self.models = _FakeModels(text=text, raises=raises, script=script)


def _planner(client, **kw):
    # Instant retries in tests.
    kw.setdefault("sleep", lambda _s: None)
    from orchestrator.planner import GeminiPlanner as _GP

    return _GP(client=client, **kw)


def test_compose_includes_system_context_and_task():
    prompt = GeminiPlanner.compose("client is acme", "build a thing")
    assert "solutions architect" in prompt.lower()  # system framing
    assert "client is acme" in prompt
    assert "build a thing" in prompt
    assert "PLAN ONLY" in prompt


def test_compose_handles_empty_context():
    prompt = GeminiPlanner.compose("", "just the task")
    assert "just the task" in prompt
    assert "Client context" not in prompt  # section omitted when no context


def test_plan_success():
    p = _planner(_FakeClient(text="here is the plan"))
    r = p.plan("ctx", "task")
    assert isinstance(r, PlanResult)
    assert r.success is True
    assert r.text == "here is the plan"


def test_plan_empty_response_is_failure():
    p = _planner(_FakeClient(text=""), max_retries=0)
    r = p.plan("ctx", "task")
    assert r.success is False
    assert "throttled" in r.error.lower()


def test_plan_transient_503_is_retried_then_succeeds():
    # First two calls 503, third returns text -> retry should recover.
    client = _FakeClient(
        script=[
            ("raise", RuntimeError("503 UNAVAILABLE high demand")),
            ("raise", RuntimeError("503 UNAVAILABLE high demand")),
            ("text", "recovered plan"),
        ]
    )
    p = _planner(client, max_retries=3)
    r = p.plan("ctx", "task")
    assert r.success is True
    assert r.text == "recovered plan"
    assert len(client.models.calls) == 3  # it actually retried


def test_plan_non_transient_error_is_not_retried():
    client = _FakeClient(raises=ValueError("400 INVALID_ARGUMENT bad request"))
    p = _planner(client, max_retries=3)
    r = p.plan("ctx", "task")
    assert r.success is False
    assert "400" in r.error
    assert len(client.models.calls) == 1  # no retries on a non-transient error


def test_plan_exhausts_retries_and_surfaces_error():
    client = _FakeClient(raises=RuntimeError("503 UNAVAILABLE"))
    p = _planner(client, max_retries=2)
    r = p.plan("ctx", "task")
    assert r.success is False
    assert "503" in r.error
    assert len(client.models.calls) == 3  # initial + 2 retries


def test_plan_passes_model_through():
    fake = _FakeClient(text="ok")
    p = _planner(fake, model="gemini-2.5-pro")
    p.plan("c", "t")
    assert fake.models.calls[0]["model"] == "gemini-2.5-pro"
