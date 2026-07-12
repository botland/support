from __future__ import annotations

import asyncio
import json
import logging
import os
import shlex
import subprocess
import time
from collections.abc import AsyncIterator
from pathlib import Path

from .errors import CLIPermanentError, CLITransientError
from .guide_parse import GuideParseError, parse_guide_reply
from .guide_prompt import (
    default_knowledge_root,
    knowledge_index,
    load_guide_prompt_template,
    render_guide_prompt,
)

logger = logging.getLogger(__name__)


def _truthy(name: str, default: str = "false") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes")


def _artifact_dir(session_id: str) -> Path:
    root = Path(os.environ.get("GUIDE_ARTIFACT_ROOT", "/data/guide"))
    path = root / (session_id or "ephemeral")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _schema_path() -> Path:
    env = os.environ.get("GUIDE_REPLY_SCHEMA", "").strip()
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2] / "schemas" / "guide-reply.v1.json"


def partial_json_string_value(blob: str, key: str = "content") -> str:
    """Extract a JSON string field from incomplete object text (streaming)."""
    marker = f'"{key}"'
    idx = blob.find(marker)
    if idx < 0:
        return ""
    colon = blob.find(":", idx + len(marker))
    if colon < 0:
        return ""
    i = colon + 1
    n = len(blob)
    while i < n and blob[i].isspace():
        i += 1
    if i >= n or blob[i] != '"':
        return ""
    i += 1
    out: list[str] = []
    while i < n:
        ch = blob[i]
        if ch == "\\":
            if i + 1 >= n:
                break
            nxt = blob[i + 1]
            escapes = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "/": "/"}
            out.append(escapes.get(nxt, nxt))
            i += 2
            continue
        if ch == '"':
            break
        out.append(ch)
        i += 1
    return "".join(out)


class SubprocessGuideAdapter:
    """Invoke external AI CLI for product-guide replies (no code worktrees)."""

    def __init__(self) -> None:
        command = os.environ.get("GUIDE_AI_CLI_COMMAND", "").strip()
        if not command:
            command = os.environ.get("AI_CLI_COMMAND", "").strip()
        if not command:
            raise CLIPermanentError("GUIDE_AI_CLI_COMMAND is not configured")
        self.command = shlex.split(command)
        self.timeout_sec = int(
            os.environ.get("GUIDE_AI_CLI_TIMEOUT_SEC")
            or os.environ.get("AI_CLI_TIMEOUT_SEC", "120")
        )
        self.use_prompt_file = _truthy("GUIDE_AI_CLI_USE_PROMPT_FILE", "true")
        self.chunk_chars = int(os.environ.get("GUIDE_STREAM_CHUNK_CHARS", "48"))
        self.grok_bin = os.environ.get("GROK_BIN", "grok").strip() or "grok"
        self.max_turns = int(
            os.environ.get("GUIDE_AI_GROK_MAX_TURNS")
            or os.environ.get("AI_GROK_MAX_TURNS", "20")
        )
        # Prefer true Grok token streaming when binary is grok (or forced)
        self.native_stream = _truthy("GUIDE_NATIVE_STREAM", "true")

    def _build_prompt(
        self,
        *,
        user_message: str,
        history: list[dict],
        locale: str,
    ) -> str:
        template = load_guide_prompt_template()
        knowledge = knowledge_index(default_knowledge_root())
        prompt = render_guide_prompt(
            template=template,
            user_message=user_message,
            history=history,
            locale=locale,
        )
        if knowledge:
            prompt = (
                f"{prompt}\n\n---\nKnowledge pack (read-only product facts):\n{knowledge}\n"
            )
        return prompt

    def _prepare_artifacts(
        self,
        *,
        prompt: str,
        history: list[dict],
        session_id: str,
    ) -> tuple[Path, Path, Path]:
        ai_dir = _artifact_dir(session_id)
        prompt_path = ai_dir / "prompt.txt"
        prompt_path.write_text(prompt, encoding="utf-8")
        (ai_dir / "history.json").write_text(
            json.dumps(history, indent=2),
            encoding="utf-8",
        )
        knowledge_root = default_knowledge_root()
        return ai_dir, prompt_path, knowledge_root

    async def chat(
        self,
        *,
        user_message: str,
        history: list[dict],
        locale: str = "en",
        session_id: str = "",
    ) -> str:
        return await asyncio.to_thread(
            self._run,
            user_message=user_message,
            history=history,
            locale=locale,
            session_id=session_id,
        )

    async def chat_stream(
        self,
        *,
        user_message: str,
        history: list[dict],
        locale: str = "en",
        session_id: str = "",
    ) -> AsyncIterator[str]:
        if self.native_stream and self._can_native_stream():
            async for chunk in self._stream_grok_native(
                user_message=user_message,
                history=history,
                locale=locale,
                session_id=session_id,
            ):
                yield chunk
            return

        # Fallback: full completion then paced chunks (tests / non-Grok CLI)
        text = await self.chat(
            user_message=user_message,
            history=history,
            locale=locale,
            session_id=session_id,
        )
        size = max(8, self.chunk_chars)
        for i in range(0, len(text), size):
            yield text[i : i + size]
            await asyncio.sleep(0.01)

    def _can_native_stream(self) -> bool:
        """Native stream when command is the Grok guide wrapper or GROK_BIN is available."""
        joined = " ".join(self.command)
        if "ai_guide_grok" in joined or "grok" in Path(self.command[0]).name:
            return True
        # Explicit override via env even with custom commands
        return _truthy("GUIDE_FORCE_NATIVE_STREAM", "false")

    async def _stream_grok_native(
        self,
        *,
        user_message: str,
        history: list[dict],
        locale: str,
        session_id: str,
    ) -> AsyncIterator[str]:
        prompt = self._build_prompt(
            user_message=user_message,
            history=history,
            locale=locale,
        )
        ai_dir, prompt_path, knowledge_root = self._prepare_artifacts(
            prompt=prompt,
            history=history,
            session_id=session_id,
        )
        schema = _schema_path()
        if not schema.is_file():
            raise CLIPermanentError(f"Guide reply schema not found: {schema}")

        try:
            schema_json = schema.read_text(encoding="utf-8")
        except OSError as exc:
            raise CLIPermanentError(f"Cannot read schema: {exc}") from exc

        cmd = [
            self.grok_bin,
            "--prompt-file",
            str(prompt_path),
            "--output-format",
            "streaming-json",
            "--json-schema",
            schema_json,
            "--always-approve",
            "--max-turns",
            str(self.max_turns),
            "--disable-web-search",
        ]
        if knowledge_root.is_dir():
            cmd.extend(["--cwd", str(knowledge_root)])

        env = os.environ.copy()
        env["AI_PROMPT_FILE"] = str(prompt_path)
        env["AI_ARTIFACT_DIR"] = str(ai_dir)
        env["GUIDE_SESSION_ID"] = session_id
        env["GUIDE_KNOWLEDGE_ROOT"] = str(knowledge_root)

        logger.info(
            "Guide native stream start session=%s cmd=%s",
            session_id,
            self.grok_bin,
        )

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=str(knowledge_root) if knowledge_root.is_dir() else None,
            )
        except OSError as exc:
            raise CLIPermanentError(f"Failed to start Grok for streaming: {exc}") from exc

        assert proc.stdout is not None
        raw_lines: list[str] = []
        text_acc = ""
        content_so_far = ""
        deadline = time.monotonic() + self.timeout_sec
        stderr_task = asyncio.create_task(proc.stderr.read() if proc.stderr else asyncio.sleep(0))

        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    proc.kill()
                    await proc.wait()
                    raise CLITransientError(
                        f"Guide AI CLI timed out after {self.timeout_sec}s"
                    )
                try:
                    line_b = await asyncio.wait_for(
                        proc.stdout.readline(),
                        timeout=min(remaining, 30.0),
                    )
                except asyncio.TimeoutError:
                    if proc.returncode is not None:
                        break
                    continue

                if not line_b:
                    break

                line = line_b.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                raw_lines.append(line)

                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue

                etype = event.get("type")
                if etype == "text":
                    text_acc += str(event.get("data") or "")
                    new_content = partial_json_string_value(text_acc, "content")
                    if len(new_content) > len(content_so_far):
                        delta = new_content[len(content_so_far) :]
                        content_so_far = new_content
                        yield delta
                elif etype == "end":
                    so = event.get("structuredOutput") or event.get("structured_output")
                    final = None
                    if isinstance(so, dict) and isinstance(so.get("content"), str):
                        final = so["content"]
                    elif isinstance(so, str) and so.strip():
                        try:
                            parsed = json.loads(so)
                            if isinstance(parsed, dict) and isinstance(
                                parsed.get("content"), str
                            ):
                                final = parsed["content"]
                        except json.JSONDecodeError:
                            pass
                    if final is None and text_acc:
                        try:
                            final = parse_guide_reply(text_acc)
                        except GuideParseError:
                            final = partial_json_string_value(text_acc) or None
                    if final:
                        if len(final) > len(content_so_far):
                            yield final[len(content_so_far) :]
                        content_so_far = final
                    break
        finally:
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except (asyncio.TimeoutError, ProcessLookupError):
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
                await proc.wait()

            stderr_data = b""
            try:
                stderr_data = await asyncio.wait_for(stderr_task, timeout=2)
            except (asyncio.TimeoutError, Exception):  # noqa: BLE001
                pass
            stderr_text = (
                stderr_data.decode("utf-8", errors="replace")
                if isinstance(stderr_data, (bytes, bytearray))
                else ""
            )
            self._save_logs(
                ai_dir,
                "\n".join(raw_lines),
                stderr_text,
            )

        if proc.returncode not in (0, None) and not content_so_far:
            detail = (stderr_text or "").strip()[-500:]
            if proc.returncode in (124, 137):
                raise CLITransientError(
                    f"Guide AI CLI exited {proc.returncode}: {detail}"
                )
            raise CLIPermanentError(
                f"Guide AI CLI exited {proc.returncode}: {detail}"
            )

        if not content_so_far.strip():
            raise CLITransientError("Guide AI stream produced empty content")

    def _run(
        self,
        *,
        user_message: str,
        history: list[dict],
        locale: str,
        session_id: str,
    ) -> str:
        prompt = self._build_prompt(
            user_message=user_message,
            history=history,
            locale=locale,
        )
        ai_dir, prompt_path, knowledge_root = self._prepare_artifacts(
            prompt=prompt,
            history=history,
            session_id=session_id,
        )

        env = os.environ.copy()
        env["AI_PROMPT_FILE"] = str(prompt_path)
        env["AI_ARTIFACT_DIR"] = str(ai_dir)
        env["GUIDE_SESSION_ID"] = session_id
        env["GUIDE_KNOWLEDGE_ROOT"] = str(knowledge_root)
        env["AI_CODE_ROOT"] = str(knowledge_root) if knowledge_root.is_dir() else ""

        cmd = list(self.command)
        joined = " ".join(self.command)
        if "{prompt_file}" in joined:
            cmd = [p.replace("{prompt_file}", str(prompt_path)) for p in cmd]
        elif self.use_prompt_file and str(prompt_path) not in cmd:
            cmd = [*cmd, str(prompt_path)]

        cwd = str(knowledge_root) if knowledge_root.is_dir() else None

        try:
            completed = subprocess.run(
                cmd,
                input=None if self.use_prompt_file else prompt,
                capture_output=True,
                text=True,
                timeout=self.timeout_sec,
                env=env,
                cwd=cwd,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            self._save_logs(ai_dir, "", f"timeout after {self.timeout_sec}s")
            raise CLITransientError(f"Guide AI CLI timed out after {self.timeout_sec}s") from exc
        except OSError as exc:
            self._save_logs(ai_dir, "", str(exc))
            raise CLIPermanentError(f"Failed to start guide AI CLI: {exc}") from exc

        self._save_logs(ai_dir, completed.stdout or "", completed.stderr or "")

        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()[-500:]
            if completed.returncode in (124, 137):
                raise CLITransientError(f"Guide AI CLI exited {completed.returncode}: {detail}")
            raise CLIPermanentError(f"Guide AI CLI exited {completed.returncode}: {detail}")

        stdout = completed.stdout or ""
        if not stdout.strip():
            raise CLITransientError("Guide AI CLI produced empty stdout")

        try:
            return parse_guide_reply(stdout)
        except GuideParseError as exc:
            raise CLIPermanentError(str(exc)) from exc

    @staticmethod
    def _save_logs(ai_dir: Path, stdout: str, stderr: str) -> None:
        try:
            (ai_dir / "cli_stdout.txt").write_text(stdout, encoding="utf-8")
            (ai_dir / "cli_stderr.txt").write_text(stderr, encoding="utf-8")
        except OSError as exc:
            logger.warning("Could not write guide CLI logs under %s: %s", ai_dir, exc)
