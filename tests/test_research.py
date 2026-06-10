"""Tests for shared/research.py — offline via a fake google-genai client."""
import json

from shared.research import (
    _extract_json,
    _grounding_urls,
    _normalize,
    research_customer,
)


# --- fake genai client plumbing ---


class _Web:
    def __init__(self, uri, title=""):
        self.uri = uri
        self.title = title


class _Chunk:
    def __init__(self, web):
        self.web = web


class _Meta:
    def __init__(self, chunks):
        self.grounding_chunks = chunks


class _Cand:
    def __init__(self, meta):
        self.grounding_metadata = meta


class _Resp:
    def __init__(self, text, urls=()):
        self.text = text
        chunks = [_Chunk(_Web(u, "t")) for u in urls]
        self.candidates = [_Cand(_Meta(chunks))]


class _Models:
    def __init__(self, script):
        self.script = list(script)  # list of ("text", _Resp) | ("raise", exc)
        self.calls = 0

    def generate_content(self, *, model, contents, config=None):
        self.calls += 1
        kind, val = self.script.pop(0)
        if kind == "raise":
            raise val
        return val


class _Client:
    def __init__(self, script):
        self.models = _Models(script)


def _noop_sleep(_):
    pass


# --- _extract_json ---


def test_extract_json_fenced():
    assert _extract_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_extract_json_raw_with_prose():
    assert _extract_json('Here you go: {"a": 1, "b": 2} cheers') == {"a": 1, "b": 2}


def test_extract_json_invalid_returns_none():
    assert _extract_json("not json at all") is None
    assert _extract_json("") is None


# --- _grounding_urls ---


def test_grounding_urls_extracts_real_uris():
    resp = _Resp("x", urls=["https://a.com/1", "https://b.com/2"])
    urls = _grounding_urls(resp)
    assert [u["url"] for u in urls] == ["https://a.com/1", "https://b.com/2"]


def test_grounding_urls_tolerates_missing():
    class Empty:
        candidates = []

    assert _grounding_urls(Empty()) == []


# --- _normalize ---


def test_normalize_backfills_source_url_from_grounding():
    obj = {
        "has_signal": True,
        "signal_type": "expansion",
        "severity": "high",
        "summary": "opened a new clinic",
        "evidence": [{"claim": "new clinic in Austin", "source_url": ""}],
        "confidence": 0.8,
    }
    out = _normalize(obj, "Acme", [{"url": "https://real.com/x", "title": "t"}])
    assert out["evidence"][0]["source_url"] == "https://real.com/x"
    assert out["has_signal"] is True
    assert out["name"] == "Acme"


def test_normalize_clamps_and_validates():
    obj = {
        "has_signal": True,
        "signal_type": "bogus",
        "severity": "extreme",
        "summary": "x",
        "evidence": [],
        "confidence": 5,
    }
    out = _normalize(obj, "Acme", [])
    assert out["signal_type"] == "neutral"  # invalid -> default
    assert out["severity"] == "low"  # invalid -> default
    assert out["confidence"] == 1.0  # clamped


# --- research_customer end to end (fake client) ---


def test_research_customer_success():
    payload = json.dumps(
        {
            "has_signal": True,
            "signal_type": "expansion",
            "severity": "high",
            "summary": "opened 3 new clinics",
            "evidence": [{"claim": "3 new clinics", "source_url": "https://news.com/a"}],
            "confidence": 0.9,
        }
    )
    client = _Client([("text", _Resp(payload, urls=["https://news.com/a"]))])
    out = research_customer("Milan Laser", "Omaha", "medspa", client=client, sleep=_noop_sleep)
    assert out["has_signal"] is True
    assert out["severity"] == "high"
    assert out["evidence"][0]["source_url"].startswith("http")
    assert out["error"] == ""


def test_research_customer_empty_name():
    out = research_customer("", client=_Client([]), sleep=_noop_sleep)
    assert out["has_signal"] is False
    assert "empty" in out["error"].lower()


def test_research_customer_transient_retry_then_success():
    payload = json.dumps({"has_signal": False, "signal_type": "neutral", "severity": "low",
                          "summary": "", "evidence": [], "confidence": 0.1})
    client = _Client(
        [
            ("raise", RuntimeError("503 UNAVAILABLE")),
            ("text", _Resp(payload)),
        ]
    )
    out = research_customer("X", client=client, max_retries=3, sleep=_noop_sleep)
    assert out["error"] == ""
    assert client.models.calls == 2


def test_research_customer_parse_failure_surfaces_error():
    client = _Client([("text", _Resp("totally not json"))])
    out = research_customer("X", client=client, max_retries=0, sleep=_noop_sleep)
    assert out["has_signal"] is False
    assert "json" in out["error"].lower()


def test_research_customer_non_transient_not_retried():
    client = _Client([("raise", ValueError("400 INVALID_ARGUMENT"))])
    out = research_customer("X", client=client, max_retries=3, sleep=_noop_sleep)
    assert out["has_signal"] is False
    assert client.models.calls == 1
