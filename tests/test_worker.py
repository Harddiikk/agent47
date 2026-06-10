"""Tests for the GeminiWorker (orchestrator step 1).

Command-building and parsing are pure and tested offline. A real end-to-end
Gemini call is gated behind RUN_GEMINI_SMOKE=1 so `make test` stays fast/free.
"""
import json
import os
from pathlib import Path

import pytest

from orchestrator.worker import PLAN, YOLO, GeminiWorker, WorkerResult


# --- Command construction (pure) ---


def test_build_command_plan_basics():
    w = GeminiWorker(Path("/tmp/ws"), model="gemini-2.5-flash")
    cmd = w.build_command("do the thing", PLAN)
    assert cmd[0] == "gemini"
    # headless prompt
    assert "-p" in cmd and "do the thing" in cmd
    # structured output
    assert cmd[cmd.index("-o") + 1] == "json"
    # read-only approval mode
    assert cmd[cmd.index("--approval-mode") + 1] == "plan"
    # fresh workspaces aren't trusted -> must skip-trust
    assert "--skip-trust" in cmd
    # model wired through
    assert cmd[cmd.index("-m") + 1] == "gemini-2.5-flash"
    # no session flags unless asked
    assert "--session-id" not in cmd and "--resume" not in cmd


def test_build_command_session_id():
    w = GeminiWorker("/tmp/ws")
    cmd = w.build_command("x", PLAN, session_id="uuid-123")
    assert cmd[cmd.index("--session-id") + 1] == "uuid-123"


def test_build_command_resume_yolo():
    w = GeminiWorker("/tmp/ws")
    cmd = w.build_command("build it", YOLO, resume="uuid-123")
    assert cmd[cmd.index("--approval-mode") + 1] == "yolo"
    assert cmd[cmd.index("--resume") + 1] == "uuid-123"


# --- Output parsing (pure) ---


def test_parse_success_extracts_fields():
    stdout = json.dumps(
        {
            "session_id": "abc-def",
            "response": "here is the plan",
            "stats": {"files": {"totalLinesAdded": 12, "totalLinesRemoved": 3}},
        }
    )
    r = GeminiWorker.parse(stdout, "", 0)
    assert isinstance(r, WorkerResult)
    assert r.success is True
    assert r.session_id == "abc-def"
    assert r.response == "here is the plan"
    assert r.lines_added == 12
    assert r.lines_removed == 3
    assert r.exit_code == 0


def test_parse_nonzero_exit_is_failure():
    r = GeminiWorker.parse("", "boom", 55)
    assert r.success is False
    assert r.exit_code == 55
    assert r.stderr == "boom"


def test_parse_non_json_stdout_is_tolerated():
    # Non-JSON stdout shouldn't crash; raw text becomes the response.
    r = GeminiWorker.parse("not json output", "", 0)
    assert r.success is True  # success follows exit code, not parse-ability
    assert r.response == "not json output"
    assert r.session_id is None
    assert r.lines_added == 0


def test_parse_missing_stats_defaults_zero():
    r = GeminiWorker.parse(json.dumps({"session_id": "s", "response": "ok"}), "", 0)
    assert r.lines_added == 0 and r.lines_removed == 0


# --- Real end-to-end smoke (opt-in) ---


@pytest.mark.skipif(
    not os.getenv("RUN_GEMINI_SMOKE"),
    reason="hits the real Gemini API; set RUN_GEMINI_SMOKE=1 to run",
)
def test_real_plan_smoke(tmp_path):
    w = GeminiWorker(tmp_path)
    r = w.plan("Reply with exactly the word: pong")
    # The wrapper contract must always hold: clean exit + a resumable session id.
    assert r.success, f"exit={r.exit_code} stderr={r.stderr}"
    assert r.session_id  # a session id we could resume after approval
    # Content can be empty under free-tier throttling (silent 429/503 retries),
    # which is an API condition, not a wrapper bug — only assert it when present.
    if r.response:
        assert "pong" in r.response.lower()
    else:
        pytest.skip("empty response — Gemini free-tier throttled this run")
