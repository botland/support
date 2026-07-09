from __future__ import annotations

import asyncio
import json
import logging
import os
import shlex
import subprocess
from pathlib import Path

from ..code_context.manager import REPO_BACKEND, REPO_CONSOLE, ticket_ai_dir
from ..schemas import DiagnosisResult, DiagnosticBundle
from .errors import CLIPermanentError, CLITransientError
from .parse import DiagnosisParseError, parse_diagnosis_result
from .prompt import load_prompt_template, render_prompt

logger = logging.getLogger(__name__)


def _truthy(name: str, default: str = "false") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes")


def _primary_code_root(code_roots: list[Path]) -> Path | None:
    """Pick agent CWD / AI_CODE_ROOT: backend preferred, then console, then first."""
    if not code_roots:
        return None
    preference = os.environ.get("AI_CLI_PRIMARY_ROOT", "backend").strip().lower()
    by_name = {path.name: path for path in code_roots}
    if preference == "first":
        return code_roots[0]
    if preference == "console":
        return by_name.get(REPO_CONSOLE) or by_name.get(REPO_BACKEND) or code_roots[0]
    # default: backend
    return by_name.get(REPO_BACKEND) or by_name.get(REPO_CONSOLE) or code_roots[0]


def expand_command_placeholders(
    command: list[str],
    *,
    prompt_file: str = "",
    bundle_file: str = "",
    code_root: str = "",
    code_roots: str = "",
    ticket_id: str = "",
) -> list[str]:
    """Replace {prompt_file}, {bundle_file}, {code_root}, {code_roots}, {ticket_id}."""
    mapping = {
        "{prompt_file}": prompt_file,
        "{bundle_file}": bundle_file,
        "{code_root}": code_root,
        "{code_roots}": code_roots,
        "{ticket_id}": ticket_id,
    }

    def _sub(part: str) -> str:
        out = part
        for key, value in mapping.items():
            out = out.replace(key, value)
        return out

    return [_sub(part) for part in command]


def write_diagnosis_artifacts(
    *,
    ticket_id: str,
    bundle: DiagnosticBundle,
    prompt: str,
    code_roots: list[Path],
) -> tuple[Path, Path, Path]:
    """Write prompt + bundle under `{worktree}/{ticket_id}/_ai/`. Returns (ai_dir, prompt, bundle)."""
    if ticket_id.strip():
        ai_dir = ticket_ai_dir(ticket_id)
    else:
        ai_dir = Path(os.environ.get("TMPDIR", "/tmp")) / "support-ai-ephemeral"
    ai_dir.mkdir(parents=True, exist_ok=True)

    prompt_path = ai_dir / "prompt.txt"
    bundle_path = ai_dir / "bundle.json"
    roots_path = ai_dir / "code_roots.txt"

    prompt_path.write_text(prompt, encoding="utf-8")
    bundle_path.write_text(
        json.dumps(bundle.model_dump(), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    roots_path.write_text(
        "\n".join(str(path) for path in code_roots) + ("\n" if code_roots else ""),
        encoding="utf-8",
    )
    return ai_dir, prompt_path, bundle_path


class SubprocessCLIAdapter:
    """Invokes a configured external AI CLI (e.g. Grok) and parses DiagnosisResult JSON."""

    def __init__(self) -> None:
        command = os.environ.get("AI_CLI_COMMAND", "").strip()
        if not command:
            raise CLIPermanentError("AI_CLI_COMMAND is not configured")
        self.command = shlex.split(command)
        self.timeout_sec = int(os.environ.get("AI_CLI_TIMEOUT_SEC", "120"))
        self.use_prompt_file = _truthy("AI_CLI_USE_PROMPT_FILE", "false")
        self.cwd_mode = os.environ.get("AI_CLI_CWD", "code_root").strip().lower()

    async def diagnose(
        self,
        *,
        bundle: DiagnosticBundle,
        code_roots: list[Path],
        prompt_template: str,
        ticket_id: str = "",
    ) -> DiagnosisResult:
        template = prompt_template or load_prompt_template()
        prompt = render_prompt(template=template, bundle=bundle, code_roots=code_roots)
        ai_dir, prompt_path, bundle_path = write_diagnosis_artifacts(
            ticket_id=ticket_id,
            bundle=bundle,
            prompt=prompt,
            code_roots=code_roots,
        )
        primary = _primary_code_root(code_roots)
        stdout = await asyncio.to_thread(
            self._run_cli,
            prompt=prompt,
            code_roots=code_roots,
            primary=primary,
            prompt_path=prompt_path,
            bundle_path=bundle_path,
            ai_dir=ai_dir,
            ticket_id=ticket_id,
        )
        try:
            return parse_diagnosis_result(stdout)
        except DiagnosisParseError as exc:
            raise CLIPermanentError(str(exc)) from exc

    def _run_cli(
        self,
        *,
        prompt: str,
        code_roots: list[Path],
        primary: Path | None,
        prompt_path: Path,
        bundle_path: Path,
        ai_dir: Path,
        ticket_id: str,
    ) -> str:
        env = os.environ.copy()
        roots_joined = os.pathsep.join(str(path) for path in code_roots)
        env["AI_CODE_ROOTS"] = roots_joined
        env["AI_CODE_ROOT"] = str(primary) if primary else ""
        env["AI_PROMPT_FILE"] = str(prompt_path)
        env["AI_BUNDLE_FILE"] = str(bundle_path)
        env["AI_ARTIFACT_DIR"] = str(ai_dir)
        env["AI_TICKET_ID"] = ticket_id

        cwd: str | None = None
        if self.cwd_mode == "code_root" and primary is not None:
            cwd = str(primary)

        cmd = expand_command_placeholders(
            list(self.command),
            prompt_file=str(prompt_path),
            bundle_file=str(bundle_path),
            code_root=str(primary) if primary else "",
            code_roots=roots_joined,
            ticket_id=ticket_id,
        )

        if self.use_prompt_file:
            # If command has no {prompt_file}, append path for simple tools.
            if "{prompt_file}" not in " ".join(self.command) and str(prompt_path) not in cmd:
                cmd = [*cmd, str(prompt_path)]
            stdin_data = None
        else:
            stdin_data = prompt

        try:
            completed = subprocess.run(
                cmd,
                input=stdin_data,
                capture_output=True,
                text=True,
                timeout=self.timeout_sec,
                env=env,
                cwd=cwd,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            self._save_cli_logs(ai_dir, stdout="", stderr=f"timeout after {self.timeout_sec}s")
            raise CLITransientError(f"AI CLI timed out after {self.timeout_sec}s") from exc
        except OSError as exc:
            self._save_cli_logs(ai_dir, stdout="", stderr=str(exc))
            raise CLIPermanentError(f"Failed to start AI CLI: {exc}") from exc

        self._save_cli_logs(ai_dir, stdout=completed.stdout or "", stderr=completed.stderr or "")

        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()[-500:]
            if completed.returncode in (124, 137):
                raise CLITransientError(f"AI CLI exited {completed.returncode}: {detail}")
            raise CLIPermanentError(f"AI CLI exited {completed.returncode}: {detail}")

        if not (completed.stdout or "").strip():
            raise CLITransientError("AI CLI produced empty stdout")

        logger.debug(
            "AI CLI finished ticket=%s bytes=%s cwd=%s",
            ticket_id,
            len(completed.stdout.encode()),
            cwd,
        )
        return completed.stdout

    @staticmethod
    def _save_cli_logs(ai_dir: Path, *, stdout: str, stderr: str) -> None:
        try:
            ai_dir.mkdir(parents=True, exist_ok=True)
            (ai_dir / "cli_stdout.txt").write_text(stdout, encoding="utf-8")
            (ai_dir / "cli_stderr.txt").write_text(stderr, encoding="utf-8")
        except OSError as exc:
            logger.warning("Could not write CLI logs under %s: %s", ai_dir, exc)
