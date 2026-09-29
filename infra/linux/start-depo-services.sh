#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"
ENV_FILE="${1:-$DEPO_ROOT/.env.local}"
depo_load_env "$ENV_FILE"
python_bin="$DEPO_ROOT/backend/.dt_venv/bin/python"
[[ -x "$python_bin" ]] || { echo "DEPO Python runtime was not found: $python_bin" >&2; exit 1; }
if [[ "${DEPO_SPARK_ENABLED:-false}" == 'true' ]]; then
  depo_assert_spark_runtime
  export SPARK_HOME="$DEPO_SPARK_HOME" JAVA_HOME="$DEPO_JAVA_HOME" PYSPARK_PYTHON="$python_bin"
fi
export PYTHONPATH="$DEPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"
host="${DEPO_SERVICE_HOST:-127.0.0.1}"
peer_host="$host"; [[ "$host" == '0.0.0.0' || "$host" == '::' ]] && peer_host='127.0.0.1'
state_dir="$DEPO_ROOT/logs/linux-services"
mkdir -p "$state_dir"

# Supply private same-host service discovery defaults. An explicit environment
# value always wins, which keeps this launcher usable behind a gateway or with
# services distributed across multiple Linux VMs.
declare -A service_urls=(
  [QIF_SERVICE_URL]="http://$peer_host:8010/api/v1"
  [ONTOLOGY_SERVICE_URL]="http://$peer_host:8011/api/v1"
  [AGENTIC_SERVICE_URL]="http://$peer_host:8012/api/v1"
  [GRAPH_SERVICE_URL]="http://$peer_host:8013/api/v1"
  [INGESTION_SERVICE_URL]="http://$peer_host:8014/api/v1"
  [OSLC_SERVICE_URL]="http://$peer_host:8015/api/v1"
  [DATA_CATALOG_URL]="http://$peer_host:8016/api/v1"
  [DATA_PRODUCT_SERVICE_URL]="http://$peer_host:8017/api/v1"
  [CEIM_SERVICE_URL]="http://$peer_host:8018/api/v1"
  [DATA_PIPELINE_SERVICE_URL]="http://$peer_host:8019/api/v1"
)
for key in "${!service_urls[@]}"; do
  [[ -n "${!key:-}" ]] || export "$key=${service_urls[$key]}"
done

"$python_bin" -m backend.agentic_service.configuration
"$python_bin" -m backend.depo_platform.database_setup

mapfile -t service_rows < <("$python_bin" - "$DEPO_ROOT/infra/deployment/services.json" <<'PY'
import json, sys
manifest=json.load(open(sys.argv[1], encoding='utf-8'))
for item in manifest['services']:
    print(f"{item['id']}|{item['module']}|{item['port']}")
for item in manifest['workers']:
    print(f"{item['id']}|{item['module']}|")
PY
)
started_pids=()
started_pid_files=()
rollback() {
  local index pid
  for index in "${!started_pids[@]}"; do
    pid="${started_pids[$index]}"
    kill "$pid" 2>/dev/null || true
    rm -f "${started_pid_files[$index]}"
  done
}
trap rollback ERR INT TERM
for row in "${service_rows[@]}"; do
  IFS='|' read -r name module port <<<"$row"
  pid_file="$state_dir/$name.pid"
  if [[ -f "$pid_file" ]]; then
    recorded_pid="$(cat "$pid_file")"
    if [[ "$recorded_pid" =~ ^[0-9]+$ ]] && kill -0 "$recorded_pid" 2>/dev/null; then
      command_line="$(tr '\0' ' ' < "/proc/$recorded_pid/cmdline" 2>/dev/null || true)"
      if [[ "$command_line" == *"$python_bin"* && "$command_line" == *"$module"* ]]; then
        echo "$name is already running with PID $recorded_pid."
        continue
      fi
      echo "PID file for $name points to an unrelated live process; refusing to continue." >&2
      exit 1
    fi
  fi
  rm -f "$pid_file"
  if [[ -n "$port" ]] && command -v ss >/dev/null 2>&1 && ss -ltnH | awk '{print $4}' | grep -Eq "(^|:)$port$"; then
    echo "Port $port for $name is already occupied by an untracked process." >&2
    exit 1
  fi
  if [[ -n "$port" ]]; then
    nohup "$python_bin" -m uvicorn "$module" --host "$host" --port "$port" --no-proxy-headers >"$state_dir/$name.out.log" 2>"$state_dir/$name.err.log" &
  else
    nohup "$python_bin" -m "$module" >"$state_dir/$name.out.log" 2>"$state_dir/$name.err.log" &
  fi
  pid=$!; echo "$pid" >"$pid_file"; started_pids+=("$pid"); started_pid_files+=("$pid_file")
done
depo_require_command curl
timeout_seconds="${DEPO_SERVICE_STARTUP_TIMEOUT_SECONDS:-300}"
for row in "${service_rows[@]}"; do
  IFS='|' read -r name _ port <<<"$row"
  [[ -n "$port" ]] || continue
  deadline=$((SECONDS + timeout_seconds))
  until curl --fail --silent --show-error --max-time 5 "http://$peer_host:$port/readyz" >/dev/null; do
    (( SECONDS < deadline )) || { echo "$name did not become ready; see $state_dir/$name.err.log" >&2; exit 1; }
    sleep 1
  done
  echo "$name is ready on port $port."
done
for row in "${service_rows[@]}"; do
  IFS='|' read -r name _ port <<<"$row"
  [[ -z "$port" ]] || continue
  pid_file="$state_dir/$name.pid"
  [[ -f "$pid_file" ]] || { echo "Worker $name has no PID file." >&2; exit 1; }
  worker_pid="$(cat "$pid_file")"
  kill -0 "$worker_pid" 2>/dev/null || { echo "Worker $name exited; see $state_dir/$name.err.log" >&2; exit 1; }
  echo "$name worker is running with PID $worker_pid."
done
trap - ERR INT TERM
echo "DEPO Linux services are ready. Stop them with infra/linux/stop-depo-services.sh."
