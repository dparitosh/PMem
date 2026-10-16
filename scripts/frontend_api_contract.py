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
CLIENT_ROOT = ROOT / "frontend" / "src"
HTTP_METHODS = {'get', 'post', 'put', 'patch', 'delete', 'head', 'options'}
SERVICE_IDS = {'dataProducts': 'data-products', 'dataPipeline': 'data-pipeline'}

# Direct execution puts ``scripts`` rather than the repository root on sys.path.
# Keep the audit usable both as a CLI and as an imported test helper.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _canonical(path: str) -> str:
    value = path.split("?", 1)[0].rstrip("/") or "/"
    return re.sub(r"\{[^}]+\}", "{}", value)


def _first_argument(source: str, start: int) -> str:
    """Read one JS argument without splitting nested calls or quoted strings."""
    depth = 0
    quote = None
    escaped = False
    for index in range(start, len(source)):
        char = source[index]
        if quote:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == quote:
                quote = None
        elif char in "'\"`":
            quote = char
        elif char in '([{':
            depth += 1
        elif char in ')]}':
            if depth == 0:
                return source[start:index].strip()
            depth -= 1
        elif char == ',' and depth == 0:
            return source[start:index].strip()
    return ''


def frontend_operations(config_text: str, sources) -> tuple[list[dict], list[dict]]:
    blocks = {name: dict(re.findall(r"(\w+)\s*:\s*setting\('[^']+'\)\s*\|\|\s*'([^']+)'", body))
              for name, body in re.findall(r'const (\w+_ENDPOINTS)\s*=\s*\{(.*?)\n\};', config_text, re.S)}
    api = re.search(r'export const API\s*=\s*\{(.*?)\n\};', config_text, re.S)
    aliases = dict(re.findall(r'(\w+)\s*:\s*(\w+_ENDPOINTS)', api.group(1))) if api else {}
    rules_block = re.search(r'const SERVICE_PATHS\s*=\s*\[(.*?)\n\];', config_text, re.S)
    rules = [(SERVICE_IDS.get(owner, owner), re.compile(pattern.replace(r'\/', '/')))
             for owner, pattern in re.findall(r"\['([^']+)', /(.+)/\]", rules_block.group(1))] if rules_block else []
    operations, unresolved = [], []
    for filename, source in sources:
        for match in re.finditer(r'\b(?:apiClient|agenticClient)\.(get|post|put|patch|delete|head|options)\s*\(', source):
            expression = _first_argument(source, match.end())
            reference = re.search(r'\bAPI\.(\w+)\.(\w+)', expression)
            path = blocks.get(aliases.get(reference[1]), {}).get(reference[2]) if reference else None
            if reference and path is None:
                # Optional operator-supplied endpoints have no default to audit.
                continue
            if path is None:
                literal = re.search(r"(?:buildUrl|buildSemanticServiceUrl|agenticUrl)\(\s*(?:'[^']+'\s*,\s*)?(['\"`])(/.*?)\1", expression, re.S)
                if not literal:
                    literal = re.match(r"(['\"`])(/.*?)\1$", expression, re.S)
                if literal:
                    path = re.sub(r'\$\{[^{}]*\}', '{value}', literal[2])
            location = {'file': str(filename), 'line': source.count('\n', 0, match.start()) + 1,
                        'method': match[1]}
            if not path or '${' in path:
                unresolved.append({**location, 'expression': expression})
                continue
            explicit = re.search(r"buildSemanticServiceUrl\(\s*'([^']+)'", expression)
            owner = SERVICE_IDS.get(explicit[1], explicit[1]) if explicit else (
                'agentic' if 'agenticUrl(' in expression else next((owner for owner, pattern in rules if pattern.search(path)), None))
            operations.append({**location, 'path': path, 'service': owner})
    return operations, unresolved


def classify_contract() -> dict[str, Any]:
    config_text = CONFIG_PATH.read_text(encoding="utf-8")
    sources = [(path.relative_to(ROOT), path.read_text(encoding='utf-8'))
               for path in sorted(CLIENT_ROOT.rglob('*.js')) if not path.name.endswith('.test.js')]
    configured, unresolved = frontend_operations(config_text, sources)
    # Agentic is one of the ten mandatory standalone services and is audited
    # against its published OpenAPI contract like every other service.
    external: set[str] = set()
    manifest = json.loads(SERVICE_MANIFEST_PATH.read_text(encoding="utf-8"))
    service_contracts: dict[str, dict] = {}
    for item in manifest.get("services", []):
        module_name, app_name = str(item["module"]).split(":", 1)
        app = getattr(importlib.import_module(module_name), app_name)
        service_contracts[str(item["id"])] = app.openapi()["paths"]

    openapi_paths = set().union(*(set(paths) for paths in service_contracts.values())) if service_contracts else set()
    # Only deployed standalone services count. Aggregate-only routes must fail
    # this audit rather than masking missing microservice implementations.
    missing, matched = [], []
    for operation in configured:
        paths = service_contracts.get(operation['service'], {})
        available = {method for path, methods in paths.items() if _canonical(path) == _canonical(operation['path'])
                     for method in methods if method in HTTP_METHODS}
        (matched if operation['method'] in available else missing).append(operation)
    return {
        "status": "pass" if configured and not missing else "fail",
        "configured_backend_endpoint_count": len(configured),
        "matched_backend_endpoint_count": len(matched),
        "external_agentic_endpoint_count": len(external),
        "service_contract_count": len(service_contracts),
        "openapi_path_count": len(openapi_paths),
        "unclassified": missing,
        "unresolved_dynamic_calls": unresolved,
        "coverage": "Static apiClient/agenticClient calls; dynamic expressions listed separately",
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
            f"{report['service_contract_count']} standalone service contracts loaded."
        )
        for operation in report["unclassified"]:
            print(f"UNCLASSIFIED {operation['method'].upper()} {operation['path']} -> {operation['service']} ({operation['file']}:{operation['line']})")
        print(f"{len(report['unresolved_dynamic_calls'])} dynamic calls require separate runtime verification.")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
