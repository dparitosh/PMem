#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
command -v python3.12 >/dev/null 2>&1 || { echo 'CPython 3.12 is required.' >&2; exit 1; }
command -v pip-compile >/dev/null 2>&1 || {
  echo 'pip-compile is required from the approved release-build toolchain; do not install build tools on a customer VM.' >&2
  exit 1
}
[[ "$(uname -s)" == 'Linux' && "$(uname -m)" == 'x86_64' ]] || {
  echo 'Generate the Linux lock only on the approved Linux x86_64 release builder.' >&2
  exit 1
}
output="$ROOT/backend/requirements-linux-lock.txt"
pip-compile \
  --python-executable "$(command -v python3.12)" \
  --generate-hashes \
  --allow-unsafe \
  --strip-extras \
  --resolver=backtracking \
  --output-file "$output" \
  "$ROOT/backend/requirements.txt"
grep -q -- '--hash=sha256:' "$output" || { echo 'Generated lock contains no artifact hashes.' >&2; exit 1; }
echo "Generated $output. Review, scan and commit it as release evidence before customer installation."
