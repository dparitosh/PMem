"""Classify frontend endpoint defaults against the backend OpenAPI document."""

from __future__ import annotations

import argparse
import importlib
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "frontend" / "src" / "config.js"
SERVICE_MANIFEST_PATH = ROOT / "infra" / "deployment" / "services.json"

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
    def named_block(name: str) -> set[str]:
        match = re.search(rf"const {name}\s*=\s*\{{(?P<body>.*?)\n\}};", config_text, flags=re.DOTALL)
        return _endpoint_defaults(match.group("body")) if match else set()

    # Agentic calls use their own opt-in client and configuration guard, so
    # retain their separate classification while auditing every other UI
    # endpoint against the independently deployed service contracts.
    external = named_block("AGENTIC_ENDPOINTS") | named_block("CHAT_ENDPOINTS")
    manifest = json.loads(SERVICE_MANIFEST_PATH.read_text(encoding="utf-8"))
    service_contracts: dict[str, set[str]] = {}
    for item in manifest.get("services", []):
        if item.get("id") == "agentic":
            continue
        module_name, app_name = str(item["module"]).split(":", 1)
        app = getattr(importlib.import_module(module_name), app_name)
        service_contracts[str(item["id"])] = set(app.openapi()["paths"])

    openapi_paths = set().union(*service_contracts.values()) if service_contracts else set()
    # The customer gateway exposes compatibility routes from the aggregate
    # application while migration to standalone service ownership continues.
    # They remain valid frontend contracts and must be included in the audit.
    aggregate_app = getattr(importlib.import_module("backend.main"), "app")
    openapi_paths.update(aggregate_app.openapi()["paths"])
    backend_shapes = {_canonical(path) for path in openapi_paths}
    backend_configured = configured - external
    missing = sorted(path for path in backend_configured if _canonical(path) not in backend_shapes)
    matched = sorted(path for path in backend_configured if _canonical(path) in backend_shapes)
    return {
        "status": "pass" if not missing else "fail",
        "configured_backend_endpoint_count": len(backend_configured),
        "matched_backend_endpoint_count": len(matched),
        "external_agentic_endpoint_count": len(external),
        "service_contract_count": len(service_contracts),
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
