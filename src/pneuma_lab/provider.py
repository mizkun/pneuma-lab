"""LLM providers.

ClaudeCodeProvider shells out to the Claude Code CLI in headless mode
(`claude -p`) — no API key is used; authentication is the user's existing
Claude Code login. `--setting-sources ""` isolates the call from the user's
global CLAUDE.md and settings (verified empirically: without it, personal
instructions leak into the agent context).
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path


class ProviderError(Exception):
    pass


class MockProvider:
    """Deterministic scripted provider for tests."""

    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        if not self._responses:
            raise ProviderError("MockProvider exhausted")
        return self._responses.pop(0)


class ClaudeCodeProvider:
    def __init__(self, model: str = "opus", timeout_seconds: float = 300.0, workdir: Path | None = None):
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.workdir = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="pneuma-agent-"))
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.total_calls = 0

    def complete(self, system: str, user: str) -> str:
        cmd = [
            "claude", "-p", user,
            "--system-prompt", system,
            "--model", self.model,
            "--tools", "",
            "--output-format", "json",
            "--no-session-persistence",
            "--setting-sources", "",
        ]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=self.timeout_seconds, cwd=self.workdir,
            )
        except subprocess.TimeoutExpired as e:
            raise ProviderError(f"claude CLI timed out after {self.timeout_seconds}s") from e
        if proc.returncode != 0:
            raise ProviderError(f"claude CLI failed (rc={proc.returncode}): {proc.stderr[-500:]}")
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            raise ProviderError(f"unparseable CLI output: {proc.stdout[-500:]}") from e
        if payload.get("is_error"):
            raise ProviderError(f"CLI reported error: {str(payload)[:500]}")
        self.total_calls += 1
        return payload["result"]
