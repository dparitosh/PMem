"""Classify frontend endpoint defaults against the backend OpenAPI document."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "frontend" / "src" / "config.js"

# Direct execution puts ``scripts`` rather than the repository root on sys.path.
# Keep the audit usable both as a CLI and as an imported test helper.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _canonical(path: str) -> str:
    value = path.split("?", 1)[0].rstrip("/") or "/"
    return re.sub(r"\{[^}]+\}", "{}", value)


def _endpoint_defaults(block: str) -> set[str]:
    return {
        value
        for value in re.findall(r"process\.env\.[A-Z0-9_]+\s*\|\|\s*'([^']+)'", block)
        if value.startswith("/")
    }


def classify_contract() -> dict[str, Any]:
    config_text = CONFIG_PATH.read_text(encoding="utf-8")
    configured = _endpoint_defaults(config_text)
    agentic_match = re.search(
        r"const AGENTIC_ENDPOINTS\s*=\s*\{(?P<body>.*?)\n\};",
        config_text,
        flags=re.DOTALL,
    )
    external = _endpoint_defaults(agentic_match.group("body")) if agentic_match else set()

    from backend.main import app

    openapi_paths = set(app.openapi()["paths"])
    backend_shapes = {_canonical(path) for path in openapi_paths}
    backend_configured = configured - external
    missing = sorted(path for path in backend_configured if _canonical(path) not in backend_shapes)
    matched = sorted(path for path in backend_configured if _canonical(path) in backend_shapes)
    return {
        "status": "pass" if not missing else "fail",
        "configured_backend_endpoint_count": len(backend_configured),
        "matched_backend_endpoint_count": len(matched),
        "external_agentic_endpoint_count": len(external),
        "openapi_path_count": len(openapi_paths),
        "unclassified": missing,
        "external_agentic": sorted(external),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args()
    report = classify_contract()
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(
            f"{report['status'].upper()}: {report['matched_backend_endpoint_count']}/"
            f"{report['configured_backend_endpoint_count']} backend endpoint defaults match "
            f"{report['openapi_path_count']} OpenAPI paths; "
            f"{report['external_agentic_endpoint_count']} agentic endpoints are external."
        )
        for path in report["unclassified"]:
            print(f"UNCLASSIFIED {path}")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
