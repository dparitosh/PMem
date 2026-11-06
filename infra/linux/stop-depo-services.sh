#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
state_dir="$ROOT/logs/linux-services"
[[ -d "$state_dir" ]] || { echo 'No Linux service state directory exists.'; exit 0; }
shopt -s nullglob
for pid_file in "$state_dir"/*.pid; do
  pid="$(cat "$pid_file")"
  if [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null; then
    command_line="$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null || true)"
    if [[ "$command_line" != *"$ROOT/backend/.dt_venv/bin/python"* || "$command_line" != *'backend.'* ]]; then
      echo "Refusing to stop unrelated PID $pid referenced by $pid_file." >&2
      continue
    fi
    kill "$pid"
    for _ in {1..30}; do kill -0 "$pid" 2>/dev/null || break; sleep 1; done
    kill -9 "$pid" 2>/dev/null || true
  fi
  rm -f "$pid_file"
done
echo 'DEPO Linux services stopped.'
