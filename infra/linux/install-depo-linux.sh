#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

ENV_FILE="$DEPO_ROOT/.env.local"
SKIP_FRONTEND=false
SKIP_DEPENDENCIES=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file) ENV_FILE="${2:?Missing --env-file value}"; shift 2 ;;
    --skip-frontend) SKIP_FRONTEND=true; shift ;;
    --skip-dependencies) SKIP_DEPENDENCIES=true; shift ;;
    -h|--help) echo "Usage: $0 [--env-file PATH] [--skip-frontend] [--skip-dependencies]"; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done
[[ "$ENV_FILE" = /* ]] || ENV_FILE="$DEPO_ROOT/$ENV_FILE"
depo_load_env "$ENV_FILE"
depo_require_command python3.12
python_version="$(python3.12 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
[[ "$python_version" == '3.12' ]] || { echo 'CPython 3.12 is required.' >&2; exit 1; }
venv="$DEPO_ROOT/backend/.dt_venv"
python_bin="$venv/bin/python"
linux_lock="$DEPO_ROOT/backend/requirements-linux-lock.txt"
if [[ "$SKIP_DEPENDENCIES" == false ]]; then
  [[ -f "$linux_lock" ]] || {
    echo 'Missing backend/requirements-linux-lock.txt. The committed Windows dependency lock cannot be installed on Linux.' >&2
    echo 'Publish the reviewed CPython 3.12 Linux x86_64 lock, or use --skip-dependencies with an approved existing runtime.' >&2
    exit 1
  }
  grep -q -- '--hash=sha256:' "$linux_lock" || { echo 'The Linux production lock contains no SHA-256 artifact hashes.' >&2; exit 1; }
  [[ -x "$python_bin" ]] || python3.12 -m venv "$venv"
  "$python_bin" -m pip install --require-hashes -r "$linux_lock"
fi
[[ -x "$python_bin" ]] || { echo "Missing backend runtime: $python_bin" >&2; exit 1; }

if [[ "$SKIP_FRONTEND" == false ]]; then
  depo_require_command node
  depo_require_command npm
  node_major="$(node -p 'process.versions.node.split(".")[0]')"
  (( node_major >= 24 )) || { echo 'Node.js 24 or newer is required.' >&2; exit 1; }
  (cd "$DEPO_ROOT/frontend" && npm ci && npm run build)
fi

(cd "$DEPO_ROOT" && "$python_bin" - <<'PY'
import importlib, json
from pathlib import Path
manifest=json.loads(Path('infra/deployment/services.json').read_text(encoding='utf-8'))
for item in manifest['services']:
    module, attribute=item['module'].split(':', 1)
    app=getattr(importlib.import_module(module), attribute)
    assert app.openapi()['paths'], f"{item['id']} produced an empty OpenAPI contract"
    print(f"PASS: {item['id']} import and OpenAPI")
for item in manifest['workers']:
    importlib.import_module(item['module'])
    print(f"PASS: {item['id']} worker import")
PY
)
if [[ "${DEPO_SPARK_ENABLED:-false}" == 'true' ]]; then
  "$SCRIPT_DIR/test-depo-spark.sh" "$ENV_FILE"
fi
echo 'DEPO Linux installation validation passed.'
echo "Start services: bash infra/linux/start-depo-services.sh '$ENV_FILE'"
