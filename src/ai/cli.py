from __future__ import annotations

import asyncio
import logging
import os
import shlex
from pathlib import Path

from ..schemas import DiagnosisResult, DiagnosticBundle
from .errors import CLIPermanentError, CLITransientError
from .parse import DiagnosisParseError, parse_diagnosis_result
from .prompt import load_prompt_template, render_prompt

logger = logging.getLogger(__name__)


class SubprocessCLIAdapter:
    """Invokes a configured external AI CLI and parses structured JSON output."""

    def __init__(self) -> None:
        command = os.environ.get("AI_CLI_COMMAND", "").strip()
        if not command:
            raise CLIPermanentError("AI_CLI_COMMAND is not configured")
        self.command = shlex.split(command)
        self.timeout_sec = int(os.environ.get("AI_CLI_TIMEOUT_SEC", "120"))
        self.use_prompt_file = os.environ.get("AI_CLI_USE_PROMPT_FILE", "").lower() in (
            "1",
            "true",
            "yes",
        )

    async def diagnose(
        self,
        *,
        bundle: DiagnosticBundle,
        code_roots: list[Path],
        prompt_template: str,
    ) -> DiagnosisResult:
        template = prompt_template or load_prompt_template()
        prompt = render_prompt(template=template, bundle=bundle, code_roots=code_roots)
        stdout = await self._run_cli(prompt, code_roots)
        try:
            return parse_diagnosis_result(stdout)
        except DiagnosisParseError as exc:
            raise CLIPermanentError(str(exc)) from exc

    async def _run_cli(self, prompt: str, code_roots: list[Path]) -> str:
        env = os.environ.copy()
        if code_roots:
            env["AI_CODE_ROOTS"] = os.pathsep.join(str(path) for path in code_roots)
            env["AI_CODE_ROOT"] = str(code_roots[0])

        if self.use_prompt_file:
            return await asyncio.to_thread(self._run_with_prompt_file, prompt, env)

        return await asyncio.to_thread(self._run_with_stdin, prompt, env)

    def _run_with_stdin(self, prompt: str, env: dict[str, str]) -> str:
        import subprocess

        try:
            completed = subprocess.run(
                self.command,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=self.timeout_sec,
                env=env,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise CLITransientError(f"AI CLI timed out after {self.timeout_sec}s") from exc
        except OSError as exc:
            raise CLIPermanentError(f"Failed to start AI CLI: {exc}") from exc

        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()[-500:]
            if completed.returncode in (124, 137):
                raise CLITransientError(f"AI CLI exited {completed.returncode}: {detail}")
            raise CLIPermanentError(f"AI CLI exited {completed.returncode}: {detail}")

        if not completed.stdout.strip():
            raise CLITransientError("AI CLI produced empty stdout")

        logger.debug("AI CLI stdout bytes=%s", len(completed.stdout.encode()))
        return completed.stdout

    def _run_with_prompt_file(self, prompt: str, env: dict[str, str]) -> str:
        import subprocess
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as handle:
            handle.write(prompt)
            prompt_path = handle.name

        cmd = [*self.command]
        if "{prompt_file}" in " ".join(cmd):
            cmd = [part.replace("{prompt_file}", prompt_path) for part in cmd]
        else:
            cmd.append(prompt_path)

        try:
            completed = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout_sec,
                env=env,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise CLITransientError(f"AI CLI timed out after {self.timeout_sec}s") from exc
        except OSError as exc:
            raise CLIPermanentError(f"Failed to start AI CLI: {exc}") from exc
        finally:
            Path(prompt_path).unlink(missing_ok=True)

        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()[-500:]
            raise CLIPermanentError(f"AI CLI exited {completed.returncode}: {detail}")
        if not completed.stdout.strip():
            raise CLITransientError("AI CLI produced empty stdout")
        return completed.stdout