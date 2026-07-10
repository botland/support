#!/usr/bin/env bash
# Production-oriented AI CLI wrapper using Grok headless mode.
# Switch tools by changing AI_CLI_COMMAND only — adapter stays AI_CLI_ADAPTER=cli.
#
# Contract (env set by SubprocessCLIAdapter):
#   AI_PROMPT_FILE, AI_BUNDLE_FILE, AI_CODE_ROOT, AI_CODE_ROOTS, AI_ARTIFACT_DIR
# Stdout: ONLY a DiagnosisResult JSON object (diagnosis-result.v1.json).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SCHEMA_PATH="${AI_DIAGNOSIS_SCHEMA:-${APP_ROOT}/schemas/diagnosis-result.v1.json}"

PROMPT_FILE="${AI_PROMPT_FILE:-}"
CODE_ROOT="${AI_CODE_ROOT:-}"
GROK_BIN="${GROK_BIN:-grok}"
ARTIFACT_DIR="${AI_ARTIFACT_DIR:-/tmp}"
mkdir -p "$ARTIFACT_DIR"

if [[ -z "$PROMPT_FILE" || ! -f "$PROMPT_FILE" ]]; then
  echo "ai_diagnose_grok: AI_PROMPT_FILE missing or not a file: ${PROMPT_FILE:-}" >&2
  exit 2
fi
if [[ ! -f "$SCHEMA_PATH" ]]; then
  echo "ai_diagnose_grok: schema not found: ${SCHEMA_PATH}" >&2
  exit 2
fi
if ! command -v "$GROK_BIN" >/dev/null 2>&1; then
  echo "ai_diagnose_grok: grok binary not found (GROK_BIN=${GROK_BIN})." >&2
  exit 2
fi

CWD_ARGS=()
if [[ -n "$CODE_ROOT" && -d "$CODE_ROOT" ]]; then
  CWD_ARGS=(--cwd "$CODE_ROOT")
fi

RAW_FILE="${ARTIFACT_DIR}/grok_raw.json"
ERR_FILE="${ARTIFACT_DIR}/grok_wrapper_stderr.txt"

# Do not pass large JSON on argv — write to file, then parse.
set +e
"${GROK_BIN}" \
  --prompt-file "$PROMPT_FILE" \
  --output-format json \
  --json-schema "$(cat "$SCHEMA_PATH")" \
  --always-approve \
  --max-turns "${AI_GROK_MAX_TURNS:-40}" \
  --disable-web-search \
  "${CWD_ARGS[@]}" \
  >"$RAW_FILE" 2>"$ERR_FILE"
GROK_RC=$?
set -e

if [[ ! -s "$RAW_FILE" ]]; then
  echo "ai_diagnose_grok: empty Grok stdout (exit=${GROK_RC}); see ${ERR_FILE}" >&2
  exit "${GROK_RC:-1}"
fi

# Extract DiagnosisResult robustly (envelope, fences, trailing prose).
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


def loads_first_object(s: str):
    """Parse first JSON value; tolerate trailing garbage (Extra data)."""
    s = s.strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    dec = json.JSONDecoder()
    for i, ch in enumerate(s):
        if ch not in "{[":
            continue
        try:
            obj, _end = dec.raw_decode(s, i)
            return obj
        except json.JSONDecodeError:
            continue
    m = fence.search(s)
    if m:
        return loads_first_object(m.group(1))
    raise ValueError("no JSON object found")


def as_diagnosis(obj):
    if not isinstance(obj, dict):
        return None
    # Grok headless envelope: { text, stopReason, sessionId, ... }
    if "verdict" not in obj and "text" in obj:
        text = obj["text"]
        if isinstance(text, (dict, list)):
            cand = text
        else:
            cand = loads_first_object(str(text))
        if isinstance(cand, dict) and "verdict" in cand:
            return cand
    if "verdict" in obj:
        return obj
    return None


try:
    outer = loads_first_object(raw)
except Exception as exc:
    raise SystemExit(f"wrapper: cannot parse Grok output: {exc}") from exc

payload = as_diagnosis(outer)
if payload is None and isinstance(outer, dict):
    # nested result field used by some formats
    for key in ("result", "data", "output"):
        if key in outer:
            payload = as_diagnosis(outer[key])
            if payload:
                break
if payload is None:
    # last resort: scan whole raw string for a DiagnosisResult-shaped object
    try:
        cand = loads_first_object(raw)
        payload = as_diagnosis(cand)
    except Exception:
        payload = None

if not isinstance(payload, dict) or "verdict" not in payload:
    raise SystemExit(
        "wrapper: no DiagnosisResult in Grok output "
        f"(keys={list(outer.keys()) if isinstance(outer, dict) else type(outer)})"
    )

required = ("verdict", "summary", "confidence", "recommended_actions")
missing = [k for k in required if k not in payload]
if missing:
    raise SystemExit(f"wrapper: DiagnosisResult missing keys: {missing}")

# Normalize optional fields
if "recommended_actions" in payload and not isinstance(payload["recommended_actions"], list):
    payload["recommended_actions"] = [str(payload["recommended_actions"])]
if "evidence" in payload and payload["evidence"] is None:
    payload["evidence"] = []

sys.stdout.write(json.dumps(payload, ensure_ascii=False))
PY

if [[ $GROK_RC -ne 0 ]]; then
  # Still succeeded if we extracted a valid diagnosis from partial/noisy output
  echo "ai_diagnose_grok: warning Grok exit=${GROK_RC} but diagnosis JSON extracted" >&2
fi
