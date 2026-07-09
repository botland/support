#!/usr/bin/env bash
# Production-oriented AI CLI wrapper using Grok headless mode.
# Switch tools by changing AI_CLI_COMMAND only — adapter stays AI_CLI_ADAPTER=cli.
#
# Contract (stdin unused; env set by SubprocessCLIAdapter):
#   AI_PROMPT_FILE   — full rendered diagnosis prompt
#   AI_BUNDLE_FILE   — diagnostic bundle JSON (same ticket worktree)
#   AI_CODE_ROOT     — primary worktree (backend preferred)
#   AI_CODE_ROOTS    — all worktrees (console + backend), os.pathsep-joined
#   AI_ARTIFACT_DIR  — ticket _ai/ directory for logs
#
# Stdout: ONLY a DiagnosisResult JSON object (diagnosis-result.v1.json).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SCHEMA_PATH="${AI_DIAGNOSIS_SCHEMA:-${APP_ROOT}/schemas/diagnosis-result.v1.json}"

PROMPT_FILE="${AI_PROMPT_FILE:-}"
CODE_ROOT="${AI_CODE_ROOT:-}"
GROK_BIN="${GROK_BIN:-grok}"

if [[ -z "$PROMPT_FILE" || ! -f "$PROMPT_FILE" ]]; then
  echo "ai_diagnose_grok: AI_PROMPT_FILE missing or not a file: ${PROMPT_FILE:-}" >&2
  exit 2
fi
if [[ ! -f "$SCHEMA_PATH" ]]; then
  echo "ai_diagnose_grok: schema not found: ${SCHEMA_PATH}" >&2
  exit 2
fi
if ! command -v "$GROK_BIN" >/dev/null 2>&1; then
  echo "ai_diagnose_grok: grok binary not found (GROK_BIN=${GROK_BIN}). Install Grok or mount ~/.grok/bin." >&2
  exit 2
fi

# Prefer backend worktree as investigation root; prompt still lists all roots.
CWD_ARGS=()
if [[ -n "$CODE_ROOT" && -d "$CODE_ROOT" ]]; then
  CWD_ARGS=(--cwd "$CODE_ROOT")
fi

# Headless Grok: structured JSON matching DiagnosisResult schema.
# --always-approve lets the agent read both worktrees without interactive prompts.
# Auth: credentials from ~/.grok/auth.json (mount host ~/.grok into the container).
RAW_OUT="$("${GROK_BIN}" \
  --prompt-file "$PROMPT_FILE" \
  --output-format json \
  --json-schema "$(cat "$SCHEMA_PATH")" \
  --always-approve \
  --max-turns "${AI_GROK_MAX_TURNS:-40}" \
  --disable-web-search \
  "${CWD_ARGS[@]}" \
  2>"${AI_ARTIFACT_DIR:-/tmp}/grok_wrapper_stderr.txt")"

# Grok headless json envelope: { "text": "...", "stopReason": ..., ... }
# text should be DiagnosisResult JSON (schema-constrained).
python3 - "$RAW_OUT" <<'PY'
import json, sys

raw = sys.argv[1]
try:
    outer = json.loads(raw)
except json.JSONDecodeError:
    # Already plain DiagnosisResult or fence-wrapped body
    text = raw
else:
    if isinstance(outer, dict) and "text" in outer:
        text = outer["text"]
        if isinstance(text, (dict, list)):
            text = json.dumps(text)
    else:
        # Schema may have been applied at top level
        text = raw

# Validate minimal shape before printing
payload = json.loads(text) if isinstance(text, str) else text
if not isinstance(payload, dict) or "verdict" not in payload:
    # try extract object from prose
    s = text if isinstance(text, str) else json.dumps(text)
    start, end = s.find("{"), s.rfind("}")
    if start >= 0 and end > start:
        payload = json.loads(s[start : end + 1])
    else:
        raise SystemExit("wrapper: no DiagnosisResult JSON in Grok output")

required = ("verdict", "summary", "confidence", "recommended_actions")
missing = [k for k in required if k not in payload]
if missing:
    raise SystemExit(f"wrapper: DiagnosisResult missing keys: {missing}")

sys.stdout.write(json.dumps(payload))
PY
