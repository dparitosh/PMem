#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
if [[ "${1:-}" == '-h' || "${1:-}" == '--help' ]]; then
  echo "Usage: $0 [ENV_FILE]"
  echo 'Set values through environment variables for automation, or run in a terminal and answer the secure prompts.'
  exit 0
fi
ENV_FILE="${1:-$ROOT/.env.local}"
[[ "$ENV_FILE" = /* ]] || ENV_FILE="$ROOT/$ENV_FILE"
[[ ! -e "$ENV_FILE" ]] || { echo "Refusing to overwrite existing configuration: $ENV_FILE" >&2; exit 1; }
command -v openssl >/dev/null 2>&1 || { echo 'openssl is required to generate service credentials.' >&2; exit 1; }
prompt() {
  local key="$1" label="$2" hidden="${3:-false}" value="${!1:-}"
  if [[ -z "$value" ]]; then
    [[ -t 0 ]] || { echo "Set $key for unattended configuration." >&2; exit 1; }
    if [[ "$hidden" == true ]]; then read -r -s -p "$label: " value; echo; else read -r -p "$label: " value; fi
    printf -v "$key" '%s' "$value"
  fi
  [[ -n "${!key}" && "${!key}" != *'<'* ]] || { echo "$key cannot be empty or a placeholder." >&2; exit 1; }
}
DEPO_SPARK_HOME="${DEPO_SPARK_HOME:-/opt/depo/runtime/spark-4.1.2-bin-hadoop3}"
DEPO_JAVA_HOME="${DEPO_JAVA_HOME:-$(dirname "$(dirname "$(readlink -f "$(command -v java)")")")}"
ARTIFACT_STORAGE="${ARTIFACT_STORAGE:-/var/lib/depo/artifacts}"
DEPO_SPARK_OUTPUT_ROOT="${DEPO_SPARK_OUTPUT_ROOT:-/var/lib/depo/spark-output}"
prompt DEPO_DATABASE_URL 'PostgreSQL URL, for example postgresql://depo_app:password@10.20.30.40:5432/depo?sslmode=require' true
prompt NEO4J_URI 'Neo4j URI, for example neo4j+s://graph.customer.example:7687'
prompt NEO4J_DATABASE 'Neo4j database name'
prompt ALLOWED_ORIGINS 'Comma-separated frontend origins, for example https://depo.customer.example,http://localhost:3000'
NEO4J_AUTH_MODE="${NEO4J_AUTH_MODE:-token}"
[[ "$NEO4J_AUTH_MODE" == 'token' || "$NEO4J_AUTH_MODE" == 'none' ]] || { echo 'NEO4J_AUTH_MODE must be token or none.' >&2; exit 1; }
if [[ "$NEO4J_AUTH_MODE" == 'token' ]]; then
  prompt NEO4J_USER 'Neo4j username'
  prompt NEO4J_PASS 'Neo4j password' true
fi
for path in "$ARTIFACT_STORAGE" "$DEPO_SPARK_HOME" "$DEPO_JAVA_HOME" "$DEPO_SPARK_OUTPUT_ROOT"; do
  [[ "$path" = /* ]] || { echo "Linux paths must be absolute: $path" >&2; exit 1; }
done
[[ -x "$DEPO_SPARK_HOME/bin/spark-submit" ]] || { echo "Spark is not installed at $DEPO_SPARK_HOME." >&2; exit 1; }
[[ -x "$DEPO_JAVA_HOME/bin/java" ]] || { echo "Java is not installed at $DEPO_JAVA_HOME." >&2; exit 1; }
for path in "$ARTIFACT_STORAGE" "$DEPO_SPARK_OUTPUT_ROOT"; do
  mkdir -p "$path"
  [[ -w "$path" ]] || { echo "Directory is not writable: $path" >&2; exit 1; }
done
secret() { openssl rand -hex 32; }
umask 077
frontend_env="$ROOT/frontend/.env.local"
[[ ! -e "$frontend_env" ]] || { echo "Refusing to overwrite existing frontend configuration: $frontend_env" >&2; exit 1; }
env_tmp="$(mktemp "${ENV_FILE}.tmp.XXXXXX")"
frontend_tmp="$(mktemp "${frontend_env}.tmp.XXXXXX")"
cleanup() { rm -f "$env_tmp" "$frontend_tmp"; }
trap cleanup EXIT INT TERM
cat > "$env_tmp" <<EOF
DEPO_DATABASE_URL=$DEPO_DATABASE_URL
DEPO_DATABASE_SCHEMA=semantic
DEPO_POSTGRES_MODE=external
DEPO_POSTGRES_CONNECT_TIMEOUT_SECONDS=10
ARTIFACT_STORAGE=$ARTIFACT_STORAGE
AUTH_MODE=token
DEPO_ALLOW_INSECURE_LOCAL_AUTH=false
ALLOWED_ORIGINS=$ALLOWED_ORIGINS
DEPO_SERVICE_HOST=127.0.0.1
GRAPH_READ_TOKEN=$(secret)
AGENTIC_APPROVAL_TOKEN=$(secret)
ONTOLOGY_APPROVAL_TOKEN=$(secret)
DATA_PRODUCT_APPROVAL_TOKEN=$(secret)
DATA_JOB_EXECUTION_TOKEN=$(secret)
DATA_JOB_APPROVAL_TOKEN=$(secret)
INGESTION_WRITE_TOKEN=$(secret)
GRAPH_PUBLICATION_TOKEN=$(secret)
CEIM_PUBLISH_APPROVAL_TOKEN=$(secret)
CATALOG_SERVICE_TOKEN=$(secret)
ARTIFACT_RETENTION_APPROVAL_TOKEN=$(secret)
CEIM_RESOLUTION_APPROVAL_TOKEN=$(secret)
SPEED_PATH_APPROVAL_TOKEN=$(secret)
SPEED_EVENT_TOKEN=$(secret)
SPARQL_FEDERATION_APPROVAL_TOKEN=$(secret)
VOCABULARY_APPROVAL_TOKEN=$(secret)
NEO4J_URI=$NEO4J_URI
NEO4J_DATABASE=$NEO4J_DATABASE
NEO4J_AUTH_MODE=$NEO4J_AUTH_MODE
NEO4J_TLS_MODE=${NEO4J_TLS_MODE:-required}
NEO4J_ENCRYPTED=${NEO4J_ENCRYPTED:-true}
NEO4J_TLS_VERIFY=${NEO4J_TLS_VERIFY:-true}
NEO4J_USER=${NEO4J_USER:-}
NEO4J_PASS=${NEO4J_PASS:-}
DEPO_SPARK_ENABLED=true
DEPO_SPARK_HOME=$DEPO_SPARK_HOME
DEPO_JAVA_HOME=$DEPO_JAVA_HOME
DEPO_SPARK_MASTER=${DEPO_SPARK_MASTER:-local[2]}
DEPO_SPARK_OUTPUT_ROOT=$DEPO_SPARK_OUTPUT_ROOT
DEPO_SPARK_NEO4J_ENABLED=${DEPO_SPARK_NEO4J_ENABLED:-false}
DEPO_SPARK_NEO4J_PACKAGE=${DEPO_SPARK_NEO4J_PACKAGE:-org.neo4j.connectors:spark:6.0.0-s_2.13}
DEPO_SPARK_POSTGRES_ENABLED=${DEPO_SPARK_POSTGRES_ENABLED:-false}
DEPO_SPARK_POSTGRES_DRIVER_JAR=${DEPO_SPARK_POSTGRES_DRIVER_JAR:-}
DEPO_PIPELINE_EXECUTION_MODE=worker
DEPO_PIPELINE_SCHEDULER_ENABLED=false
DEPO_PIPELINE_LEASE_SECONDS=300
DEPO_PIPELINE_POLL_SECONDS=5
DEPO_PIPELINE_WORKER_STALE_SECONDS=60
ONTOLOGY_AGENT_LLM_ENABLED=false
DT_AGENT_ENABLED=false
OSLC_REMOTE_ENABLED=false
DOCUMENT_OCR_PROVIDER=auto
DOCUMENT_EASYOCR_MODEL_DIR=$ARTIFACT_STORAGE/models/easyocr
DOCUMENT_EASYOCR_ALLOW_DOWNLOAD=false
DOCUMENT_OCR_GPU=false
EOF
cat > "$frontend_tmp" <<EOF
VITE_API_GATEWAY_URL=${VITE_API_GATEWAY_URL:-}
VITE_AGENTIC_ENABLED=true
VITE_AGENTIC_SERVICE_URL=${VITE_AGENTIC_SERVICE_URL:-http://127.0.0.1:8012}
VITE_REWRITE_LOCALHOST_BACKEND=true
EOF
chmod 0600 "$env_tmp"
chmod 0640 "$frontend_tmp"
mv "$env_tmp" "$ENV_FILE"
mv "$frontend_tmp" "$frontend_env"
trap - EXIT INT TERM
echo "Created $ENV_FILE and $frontend_env. Secrets were generated without printing them."
