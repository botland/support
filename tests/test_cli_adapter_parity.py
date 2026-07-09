from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.ai.cli import SubprocessCLIAdapter
from src.ai.errors import CLIPermanentError, CLITransientError


def _completed(returncode: int, stdout: str = '{"verdict":"unknown","summary":"x","confidence":"low","recommended_actions":[]}', stderr: str = ""):
    result = MagicMock()
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = stderr
    return result


@pytest.fixture
def adapter(monkeypatch):
    monkeypatch.setenv("AI_CLI_COMMAND", "echo")
    monkeypatch.delenv("AI_CLI_USE_PROMPT_FILE", raising=False)
    return SubprocessCLIAdapter()


def test_stdin_path_treats_124_as_transient(adapter):
    with patch("subprocess.run", return_value=_completed(124)) as run:
        with pytest.raises(CLITransientError):
            adapter._run_with_stdin("prompt", {})
        run.assert_called_once()


def test_stdin_path_treats_137_as_transient(adapter):
    with patch("subprocess.run", return_value=_completed(137)):
        with pytest.raises(CLITransientError):
            adapter._run_with_stdin("prompt", {})


def test_prompt_file_path_treats_124_as_permanent(adapter, monkeypatch):
    monkeypatch.setenv("AI_CLI_USE_PROMPT_FILE", "true")
    adapter = SubprocessCLIAdapter()
    with patch("subprocess.run", return_value=_completed(124)):
        with pytest.raises(CLIPermanentError):
            adapter._run_with_prompt_file("prompt", {})


def test_empty_stdout_is_transient_in_both_paths(adapter, monkeypatch):
    with patch("subprocess.run", return_value=_completed(0, stdout="   ")):
        with pytest.raises(CLITransientError):
            adapter._run_with_stdin("prompt", {})

    monkeypatch.setenv("AI_CLI_USE_PROMPT_FILE", "true")
    adapter_file = SubprocessCLIAdapter()
    with patch("subprocess.run", return_value=_completed(0, stdout="")):
        with pytest.raises(CLITransientError):
            adapter_file._run_with_prompt_file("prompt", {})