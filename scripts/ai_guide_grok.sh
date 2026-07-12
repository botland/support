#!/usr/bin/env bash
# Product-guide AI CLI wrapper (Grok headless). No code worktrees — knowledge CWD only.
# Env from SubprocessGuideAdapter: AI_PROMPT_FILE, AI_ARTIFACT_DIR, GUIDE_KNOWLEDGE_ROOT
# Stdout: GuideReply JSON { "content": "..." }
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SCHEMA_PATH="${GUIDE_REPLY_SCHEMA:-${APP_ROOT}/schemas/guide-reply.v1.json}"

PROMPT_FILE="${AI_PROMPT_FILE:-}"
GROK_BIN="${GROK_BIN:-grok}"
ARTIFACT_DIR="${AI_ARTIFACT_DIR:-/tmp}"
KNOWLEDGE_ROOT="${GUIDE_KNOWLEDGE_ROOT:-${APP_ROOT}/knowledge/product-guide}"
mkdir -p "$ARTIFACT_DIR"

if [[ -z "$PROMPT_FILE" || ! -f "$PROMPT_FILE" ]]; then
  echo "ai_guide_grok: AI_PROMPT_FILE missing or not a file: ${PROMPT_FILE:-}" >&2
  exit 2
fi
if [[ ! -f "$SCHEMA_PATH" ]]; then
  echo "ai_guide_grok: schema not found: ${SCHEMA_PATH}" >&2
  exit 2
fi
if ! command -v "$GROK_BIN" >/dev/null 2>&1; then
  echo "ai_guide_grok: grok binary not found (GROK_BIN=${GROK_BIN})." >&2
  exit 2
fi

CWD_ARGS=()
if [[ -n "$KNOWLEDGE_ROOT" && -d "$KNOWLEDGE_ROOT" ]]; then
  CWD_ARGS=(--cwd "$KNOWLEDGE_ROOT")
fi

RAW_FILE="${ARTIFACT_DIR}/grok_raw.json"
ERR_FILE="${ARTIFACT_DIR}/grok_wrapper_stderr.txt"

set +e
"${GROK_BIN}" \
  --prompt-file "$PROMPT_FILE" \
  --output-format json \
  --json-schema "$(cat "$SCHEMA_PATH")" \
  --always-approve \
  --max-turns "${GUIDE_AI_GROK_MAX_TURNS:-${AI_GROK_MAX_TURNS:-20}}" \
  --disable-web-search \
  "${CWD_ARGS[@]}" \
  >"$RAW_FILE" 2>"$ERR_FILE"
GROK_RC=$?
set -e

if [[ ! -s "$RAW_FILE" ]]; then
  echo "ai_guide_grok: empty Grok stdout (exit=${GROK_RC}); see ${ERR_FILE}" >&2
  exit "${GROK_RC:-1}"
fi

python3 - "$RAW_FILE" <<'PY'
import json
import re
import sys
from pathlib import Path

raw_path = Path(sys.argv[1])
raw = raw_path.read_text(encoding="utf-8", errors="replace").strip()
if not raw:
    raise SystemExit("wrapper: empty Grok output file")

fence = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


def iter_json_values(s: str):
    dec = json.JSONDecoder()
    i = 0
    n = len(s)
    while i < n:
        while i < n and s[i].isspace():
            i += 1
        if i >= n:
            break
        try:
            obj, end = dec.raw_decode(s, i)
        except json.JSONDecodeError:
            i += 1
            continue
        yield obj
        i = end


def content_of(obj):
    if not isinstance(obj, dict):
        return None
    c = obj.get("content")
    if isinstance(c, str) and c.strip():
        return c.strip()
    so = obj.get("structuredOutput") or obj.get("structured_output")
    if isinstance(so, dict):
        c = so.get("content")
        if isinstance(c, str) and c.strip():
            return c.strip()
    if isinstance(so, str) and so.strip():
        try:
            inner = json.loads(so)
            if isinstance(inner, dict) and isinstance(inner.get("content"), str):
                return inner["content"].strip()
        except json.JSONDecodeError:
            pass
    return None


last = None
# Prefer structuredOutput envelope, else last object with content
try:
    root = json.loads(raw)
    c = content_of(root)
    if c:
        last = c
    if isinstance(root, dict) and isinstance(root.get("text"), str):
        for obj in iter_json_values(root["text"]):
            c = content_of(obj)
            if c:
                last = c
except json.JSONDecodeError:
    pass

if last is None:
    for m in fence.finditer(raw):
        try:
            obj = json.loads(m.group(1).strip())
            c = content_of(obj)
            if c:
                last = c
        except json.JSONDecodeError:
            continue

if last is None:
    for obj in iter_json_values(raw):
        c = content_of(obj)
        if c:
            last = c

if not last:
    raise SystemExit("wrapper: no GuideReply content in Grok output")

print(json.dumps({"content": last}, ensure_ascii=False))
PY
