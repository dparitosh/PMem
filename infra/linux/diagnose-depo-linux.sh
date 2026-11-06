#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"
ENV_FILE="${1:-$DEPO_ROOT/.env.local}"
failures=0
check() { if "$@"; then echo "PASS: $*"; else echo "FAIL: $*" >&2; failures=$((failures+1)); fi; }
for command_name in python3.12 node npm java curl tar gpg openssl; do check command -v "$command_name"; done
if command -v python3.12 >/dev/null 2>&1; then check test "$(python3.12 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')" = '3.12'; fi
if command -v node >/dev/null 2>&1; then check node -e 'process.exit(Number(process.versions.node.split(".")[0]) >= 24 ? 0 : 1)'; fi
if command -v npm >/dev/null 2>&1; then
  npm_version="$(npm --version)"
  check test "$(printf '%s\n' '10.2.0' "$npm_version" | sort -V | head -n1)" = '10.2.0'
fi
check test -f "$DEPO_ROOT/backend/requirements-linux-lock.txt"
check test -f "$DEPO_ROOT/frontend/package-lock.json"
if [[ -f "$ENV_FILE" ]]; then
  depo_load_env "$ENV_FILE"
  for key in DEPO_DATABASE_URL NEO4J_URI NEO4J_DATABASE ARTIFACT_STORAGE DEPO_SPARK_HOME DEPO_JAVA_HOME DEPO_SPARK_OUTPUT_ROOT GRAPH_READ_TOKEN GRAPH_PUBLICATION_TOKEN; do
    if [[ -n "${!key:-}" && "${!key}" != *'<'* ]]; then echo "PASS: $key configured"; else echo "FAIL: $key missing or placeholder" >&2; failures=$((failures+1)); fi
  done
  if ! depo_assert_spark_runtime; then failures=$((failures+1)); fi
else
  echo "FAIL: missing $ENV_FILE" >&2; failures=$((failures+1))
fi
if [[ -x "$DEPO_ROOT/backend/.dt_venv/bin/python" && -f "$ENV_FILE" ]]; then
  if (cd "$DEPO_ROOT" && "$DEPO_ROOT/backend/.dt_venv/bin/python" -m backend.agentic_service.configuration); then
    echo 'PASS: backend configuration contract'
  else failures=$((failures+1)); fi
fi
(( failures == 0 )) || { echo "Linux preflight failed with $failures issue(s)." >&2; exit 1; }
echo 'DEPO Linux preflight passed.'
