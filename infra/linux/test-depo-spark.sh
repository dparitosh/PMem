#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

ENV_FILE="${1:-$DEPO_ROOT/.env.local}"
depo_load_env "$ENV_FILE"
depo_assert_spark_runtime
python_bin="$DEPO_ROOT/backend/.dt_venv/bin/python"
[[ -x "$python_bin" ]] || { echo "DEPO Python runtime was not found: $python_bin" >&2; exit 1; }
export SPARK_HOME="$DEPO_SPARK_HOME" JAVA_HOME="$DEPO_JAVA_HOME"
export PYSPARK_PYTHON="$python_bin" PYSPARK_DRIVER_PYTHON="$python_bin"
master="${DEPO_SPARK_MASTER:-local[2]}"
ivy_root="$DEPO_SPARK_OUTPUT_ROOT/.ivy2"
mkdir -p "$ivy_root"

"$SPARK_HOME/bin/spark-submit" --master "$master" --conf "spark.jars.ivy=$ivy_root" "$DEPO_ROOT/infra/spark/smoke_job.py"
if [[ "${DEPO_SPARK_NEO4J_ENABLED:-false}" == 'true' ]]; then
  [[ -n "${DEPO_SPARK_NEO4J_PACKAGE:-}" ]] || { echo 'DEPO_SPARK_NEO4J_PACKAGE is required.' >&2; exit 1; }
  [[ -n "${NEO4J_URI:-}" ]] || { echo 'NEO4J_URI is required.' >&2; exit 1; }
  if [[ "${NEO4J_AUTH_MODE:-token}" != 'none' ]]; then
    [[ -n "${NEO4J_USER:-}" && -n "${NEO4J_PASS:-}" ]] || { echo 'Neo4j credentials are required.' >&2; exit 1; }
  fi
  "$SPARK_HOME/bin/spark-submit" --master "$master" --conf "spark.jars.ivy=$ivy_root" --packages "$DEPO_SPARK_NEO4J_PACKAGE" "$DEPO_ROOT/infra/spark/neo4j_connector_smoke.py"
fi
if [[ "${DEPO_SPARK_POSTGRES_ENABLED:-false}" == 'true' ]]; then
  [[ -f "${DEPO_SPARK_POSTGRES_DRIVER_JAR:-}" ]] || { echo 'DEPO_SPARK_POSTGRES_DRIVER_JAR must identify an existing JDBC JAR.' >&2; exit 1; }
  "$SPARK_HOME/bin/spark-submit" --master "$master" --conf "spark.jars.ivy=$ivy_root" --jars "$DEPO_SPARK_POSTGRES_DRIVER_JAR" "$DEPO_ROOT/infra/spark/postgres_connector_smoke.py"
fi
echo 'DEPO Linux Spark validation passed.'
