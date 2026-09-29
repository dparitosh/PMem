#!/usr/bin/env bash
set -Eeuo pipefail

DEPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

depo_load_env() {
  local env_file="${1:-$DEPO_ROOT/.env.local}"
  [[ -f "$env_file" ]] || { echo "Missing DEPO environment file: $env_file" >&2; return 1; }
  local line key value
  declare -A seen_keys=()
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    [[ -z "${line//[[:space:]]/}" || "$line" =~ ^[[:space:]]*# ]] && continue
    [[ "$line" == *=* ]] || { echo "Invalid environment entry in $env_file: $line" >&2; return 1; }
    key="${line%%=*}"
    value="${line#*=}"
    key="${key#"${key%%[![:space:]]*}"}"
    key="${key%"${key##*[![:space:]]}"}"
    [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || { echo "Invalid environment key: $key" >&2; return 1; }
    [[ -z "${seen_keys[$key]:-}" ]] || { echo "Duplicate environment key in $env_file: $key" >&2; return 1; }
    seen_keys[$key]=1
    value="${value#"${value%%[![:space:]]*}"}"
    value="${value%"${value##*[![:space:]]}"}"
    if [[ ${#value} -ge 2 && (( "${value:0:1}" == '"' && "${value: -1}" == '"' ) || ( "${value:0:1}" == "'" && "${value: -1}" == "'" )) ]]; then
      value="${value:1:${#value}-2}"
    fi
    export "$key=$value"
  done < "$env_file"
  [[ -n "${NEO4J_USER:-}" ]] || export NEO4J_USER="${NEO4J_USERNAME:-}"
  [[ -n "${NEO4J_PASS:-}" ]] || export NEO4J_PASS="${NEO4J_PASSWORD:-}"
}

depo_require_command() {
  command -v "$1" >/dev/null 2>&1 || { echo "Required command is unavailable: $1" >&2; return 1; }
}

depo_assert_spark_runtime() {
  local spark_home="${DEPO_SPARK_HOME:-}" java_home="${DEPO_JAVA_HOME:-}"
  [[ -n "$spark_home" && "$spark_home" = /* ]] || { echo 'DEPO_SPARK_HOME must be an absolute Linux path.' >&2; return 1; }
  [[ -n "$java_home" && "$java_home" = /* ]] || { echo 'DEPO_JAVA_HOME must be an absolute Linux path.' >&2; return 1; }
  [[ -x "$spark_home/bin/spark-submit" ]] || { echo "Missing executable: $spark_home/bin/spark-submit" >&2; return 1; }
  [[ -f "$spark_home/python/lib/pyspark.zip" ]] || { echo "Missing file: $spark_home/python/lib/pyspark.zip" >&2; return 1; }
  compgen -G "$spark_home/python/lib/py4j-*-src.zip" >/dev/null || { echo 'Spark Py4J archive is missing.' >&2; return 1; }
  [[ -f "$spark_home/RELEASE" ]] || { echo "Missing file: $spark_home/RELEASE" >&2; return 1; }
  grep -Eq 'Spark 4\.1\.2([^0-9]|$)' "$spark_home/RELEASE" || { echo 'DEPO requires the approved Spark 4.1.2 runtime.' >&2; return 1; }
  [[ -x "$java_home/bin/java" ]] || { echo "Missing executable: $java_home/bin/java" >&2; return 1; }
  local java_major
  java_major="$("$java_home/bin/java" -version 2>&1 | sed -n '1s/.*version "\([0-9]*\).*/\1/p')"
  [[ "$java_major" == '21' ]] || { echo "DEPO requires JDK 21; configured Java is ${java_major:-unknown}." >&2; return 1; }
  [[ -n "${DEPO_SPARK_OUTPUT_ROOT:-}" && "$DEPO_SPARK_OUTPUT_ROOT" = /* ]] || { echo 'DEPO_SPARK_OUTPUT_ROOT must be an absolute Linux path.' >&2; return 1; }
  mkdir -p "$DEPO_SPARK_OUTPUT_ROOT"
  [[ -w "$DEPO_SPARK_OUTPUT_ROOT" ]] || { echo "Spark output directory is not writable: $DEPO_SPARK_OUTPUT_ROOT" >&2; return 1; }
}
