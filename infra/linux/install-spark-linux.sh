#!/usr/bin/env bash
set -Eeuo pipefail

SPARK_VERSION="4.1.2"
INSTALL_ROOT="${DEPO_LINUX_RUNTIME_ROOT:-$HOME/depo/runtime}"
DOWNLOAD_ROOT="${DEPO_LINUX_DOWNLOAD_ROOT:-$HOME/depo/downloads}"
APACHE_BASE_URL="https://archive.apache.org/dist/spark/spark-$SPARK_VERSION"

usage() {
  echo "Usage: $0 [--install-root ABSOLUTE_PATH] [--download-root ABSOLUTE_PATH]"
}
while [[ $# -gt 0 ]]; do
  case "$1" in
    --install-root) INSTALL_ROOT="${2:?Missing --install-root value}"; shift 2 ;;
    --download-root) DOWNLOAD_ROOT="${2:?Missing --download-root value}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done
[[ "$INSTALL_ROOT" = /* && "$DOWNLOAD_ROOT" = /* ]] || { echo 'Install and download roots must be absolute paths.' >&2; exit 2; }

for command_name in curl tar sha512sum gpg java; do
  command -v "$command_name" >/dev/null 2>&1 || { echo "Install required command first: $command_name" >&2; exit 1; }
done
java_major="$(java -version 2>&1 | sed -n '1s/.*version "\([0-9]*\).*/\1/p')"
[[ "$java_major" == '21' ]] || { echo "JDK 21 is required; detected Java ${java_major:-unknown}." >&2; exit 1; }
java_bin="$(readlink -f "$(command -v java)")"
java_home="$(dirname "$(dirname "$java_bin")")"

archive_name="spark-$SPARK_VERSION-bin-hadoop3.tgz"
archive="$DOWNLOAD_ROOT/$archive_name"
spark_home="$INSTALL_ROOT/spark-$SPARK_VERSION-bin-hadoop3"
mkdir -p "$DOWNLOAD_ROOT" "$INSTALL_ROOT"
[[ -w "$DOWNLOAD_ROOT" && -w "$INSTALL_ROOT" ]] || { echo 'Selected directories must be writable. Use approved ownership or run with an appropriate service account.' >&2; exit 1; }
[[ ! -e "$spark_home" ]] || { echo "Refusing to overwrite existing Spark runtime: $spark_home" >&2; exit 1; }

curl --fail --location --proto '=https' --tlsv1.2 "$APACHE_BASE_URL/$archive_name" --output "$archive"
curl --fail --location --proto '=https' --tlsv1.2 "$APACHE_BASE_URL/$archive_name.sha512" --output "$archive.sha512"
curl --fail --location --proto '=https' --tlsv1.2 "$APACHE_BASE_URL/$archive_name.asc" --output "$archive.asc"
curl --fail --location --proto '=https' --tlsv1.2 'https://downloads.apache.org/spark/KEYS' --output "$DOWNLOAD_ROOT/apache-spark-KEYS"

expected="$(awk '{print tolower($1); exit}' "$archive.sha512")"
actual="$(sha512sum "$archive" | awk '{print $1}')"
[[ "$actual" == "$expected" ]] || { echo 'Spark SHA-512 verification failed.' >&2; exit 1; }
gpg_home="$(mktemp -d)"
trap 'rm -rf "$gpg_home"' EXIT
chmod 700 "$gpg_home"
gpg --homedir "$gpg_home" --batch --import "$DOWNLOAD_ROOT/apache-spark-KEYS" >/dev/null
gpg --homedir "$gpg_home" --batch --verify "$archive.asc" "$archive"

tar -tzf "$archive" >/dev/null
tar -xzf "$archive" -C "$INSTALL_ROOT"
[[ -x "$spark_home/bin/spark-submit" && -f "$spark_home/python/lib/pyspark.zip" ]] || { echo 'Extracted Spark runtime is incomplete.' >&2; exit 1; }

cat <<EOF
Spark $SPARK_VERSION installed and cryptographically verified.
Add these exact values to the repository root .env.local:
DEPO_SPARK_ENABLED=true
DEPO_SPARK_HOME=$spark_home
DEPO_JAVA_HOME=$java_home
DEPO_SPARK_MASTER=local[2]
DEPO_SPARK_OUTPUT_ROOT=$HOME/depo/data/spark-output
EOF
