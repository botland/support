#!/bin/sh
set -e

# Mounted host clones are often owned by a non-root UID; git 2.35+ blocks that unless trusted.
if [ -n "${CODE_ROOT_APPLIANCE_CONSOLE:-}" ]; then
  git config --global --add safe.directory "$CODE_ROOT_APPLIANCE_CONSOLE"
fi
if [ -n "${CODE_ROOT_APPLIANCE_BACKEND:-}" ]; then
  git config --global --add safe.directory "$CODE_ROOT_APPLIANCE_BACKEND"
fi

exec uvicorn src.main:app --host 0.0.0.0 --port "${SUPPORT_PORT:-8090}"