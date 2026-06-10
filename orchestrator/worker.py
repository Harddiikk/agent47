"""Gemini CLI worker — the orchestrator's unit of execution.

A *worker* is a single headless `gemini` CLI run inside an isolated workspace.
The orchestrator drives a task through two phases that map directly onto the
CLI's approval modes:

  1. plan()    — read-only run (`--approval-mode plan`). Gemini analyzes the
                 task and produces a plan / architecture WITHOUT modifying
                 anything. This is the artifact that gets sent for human
                 approval (Telegram / Slack).
  2. execute() — after approval, a build run (`--approval-mode yolo`) that
                 resumes the same session and actually does the work in the
                 workspace.

Both phases run with `-o json`, so each run returns a structured `WorkerResult`
carrying the session id (to resume later), the model's response, and progress
stats (lines added/removed). Fresh workspaces are not "trusted" by the Gemini
CLI, so every run passes `--skip-trust`; isolation comes from each worker owning
its own workspace directory.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from shared.config import DEFAULT_MODEL

# CLI approval modes (see `gemini --help`):
#   plan      — read-only, no edits/commands (used for planning)
#   auto_edit — auto-approve edit tools only
#   yolo      — auto-approve all tools (used for the post-approval build)
#   default   — prompt for approval (not usable headless)
PLAN = "plan"
AUTO_EDIT = "auto_edit"
YOLO = "yolo"


@dataclass
class WorkerResult:
    """Structured outcome of one headless Gemini run."""

    success: bool
    session_id: Optional[str]
    response: str
    lines_added: int
    lines_removed: int
    exit_code: int
    raw: dict = field(default_factory=dict)
    stderr: str = ""


class GeminiWorker:
    """Launches headless Gemini CLI runs in a dedicated, isolated workspace."""

    def __init__(self, workspace: Path | str, model: str = DEFAULT_MODEL):
        self.workspace = Path(workspace)
        self.model = model

    def build_command(
        self,
        prompt: str,
        approval_mode: str,
        *,
        session_id: Optional[str] = None,
        resume: Optional[str] = None,
    ) -> list[str]:
        """Assemble the `gemini` argv. Pure and side-effect free, so it's unit-testable.

        Args:
            prompt: The instruction for this run.
            approval_mode: One of PLAN / AUTO_EDIT / YOLO.
            session_id: Start a new session with this explicit UUID.
            resume: Resume a prior session ("latest", an index, or a session id).
        """
        cmd = [
            "gemini",
            "-p", prompt,
            "-o", "json",
            "--approval-mode", approval_mode,
            "--skip-trust",
            "-m", self.model,
        ]
        if session_id:
            cmd += ["--session-id", session_id]
        if resume:
            cmd += ["--resume", resume]
        return cmd

    def run(
        self,
        prompt: str,
        approval_mode: str = PLAN,
        *,
        session_id: Optional[str] = None,
        resume: Optional[str] = None,
        timeout: int = 600,
    ) -> WorkerResult:
        """Run Gemini headlessly in the workspace and return a parsed result."""
        self.workspace.mkdir(parents=True, exist_ok=True)
        cmd = self.build_command(
            prompt, approval_mode, session_id=session_id, resume=resume
        )
        proc = subprocess.run(
            cmd,
            cwd=str(self.workspace),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return self.parse(proc.stdout, proc.stderr, proc.returncode)

    @staticmethod
    def parse(stdout: str, stderr: str, returncode: int) -> WorkerResult:
        """Parse Gemini's JSON stdout into a WorkerResult (tolerant of non-JSON)."""
        data: dict = {}
        response = stdout.strip()
        if stdout.strip():
            try:
                data = json.loads(stdout)
                response = data.get("response", "")
            except json.JSONDecodeError:
                pass  # leave raw stdout as the response; success still gated on exit code
        files = (data.get("stats") or {}).get("files") or {}
        return WorkerResult(
            success=(returncode == 0),
            session_id=data.get("session_id"),
            response=response,
            lines_added=files.get("totalLinesAdded", 0),
            lines_removed=files.get("totalLinesRemoved", 0),
            exit_code=returncode,
            raw=data,
            stderr=stderr,
        )

    # --- Phase helpers ---

    def plan(self, task: str, *, session_id: Optional[str] = None) -> WorkerResult:
        """Read-only planning run. Produces the plan/architecture for approval."""
        return self.run(task, approval_mode=PLAN, session_id=session_id)

    def execute(
        self, task: str, *, session_id: Optional[str] = None, resume: Optional[str] = None
    ) -> WorkerResult:
        """Post-approval build run. Resume the planning session and do the work."""
        return self.run(task, approval_mode=YOLO, session_id=session_id, resume=resume)
