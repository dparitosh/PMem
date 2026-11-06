#!/usr/bin/env bash
set -Eeuo pipefail
[[ "$(id -u)" -eq 0 ]] || { echo 'Run this installer as root.' >&2; exit 1; }
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT/infra/linux/common.sh"
ENV_FILE="${1:-$ROOT/.env.local}"
SERVICE_USER="${2:-depo}"
getent passwd "$SERVICE_USER" >/dev/null || { echo "Service account does not exist: $SERVICE_USER" >&2; exit 1; }
SERVICE_GROUP="$(id -gn "$SERVICE_USER")"
depo_load_env "$ENV_FILE"
for path in "$ROOT/logs" "${ARTIFACT_STORAGE:-}" "${DEPO_SPARK_OUTPUT_ROOT:-}"; do
  [[ -n "$path" && "$path" = /* ]] || { echo 'ROOT, ARTIFACT_STORAGE and DEPO_SPARK_OUTPUT_ROOT must be absolute paths.' >&2; exit 1; }
  install -d -o "$SERVICE_USER" -g "$SERVICE_GROUP" -m 0750 "$path"
done
unit=/etc/systemd/system/depo.service
sed \
  -e "s|__DEPO_USER__|$SERVICE_USER|g" \
  -e "s|__DEPO_GROUP__|$SERVICE_GROUP|g" \
  -e "s|__DEPO_ROOT__|$ROOT|g" \
  -e "s|__ARTIFACT_STORAGE__|$ARTIFACT_STORAGE|g" \
  -e "s|__SPARK_OUTPUT_ROOT__|$DEPO_SPARK_OUTPUT_ROOT|g" \
  "$ROOT/infra/linux/systemd/depo.service.template" > "$unit"
chmod 0644 "$unit"
systemd-analyze verify "$unit"
systemctl daemon-reload
systemctl enable depo.service
echo 'Installed and enabled depo.service. Start it with: sudo systemctl start depo.service'
