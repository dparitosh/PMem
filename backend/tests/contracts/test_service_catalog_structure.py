"""Validate catalog references without starting services or databases."""
import json
import ast
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_service_entrypoints_and_identifiers():
    manifest = json.loads((ROOT / "infra/deployment/services.json").read_text())
    services = manifest["services"]
    for field in ("id", "port", "apim_path"):
        assert len({item[field] for item in services}) == len(services)
    for item in services:
        module, attribute = item["module"].split(":")
        assert attribute == "app"
        assert (ROOT / (module.replace(".", "/") + ".py")).is_file()


def test_agent_tools_resolve_to_catalog_entries():
    catalog = json.loads((ROOT / "backend/agentic_service/catalog.json").read_text())
    tools = {item["id"]: item for item in catalog["tools"]}
    assert len(tools) == len(catalog["tools"])
    for agent in catalog["agents"]:
        assert set(agent["tools"]) <= tools.keys(), agent["id"]


def test_documented_services_match_deployment_inventory():
    manifest = json.loads((ROOT / "infra/deployment/services.json").read_text())
    document = (ROOT / "docs/architecture/SERVICE_CATALOG.md").read_text(encoding="utf-8")
    for service in manifest["services"]:
        package = service["module"].split(":")[0].rsplit(".", 1)[0]
        assert f"| {service['port']} | {package} |" in document, service["id"]


def test_retired_modules_have_no_source_imports():
    retired = {
        "backend.Services.ontology_reasoning_service",
        "backend.Services.ontology_taxonomy_service",
        "backend.ingestion_service.ontology_browser_router",
    }
    sources = []
    for directory, folders, files in os.walk(ROOT / "backend"):
        folders[:] = [name for name in folders if not name.startswith(".")
                      and name not in {"node_modules", "__pycache__", "site-packages", "venv"}]
        sources.extend(Path(directory) / name for name in files if name.endswith(".py"))
    for source in sources:
        tree = ast.parse(source.read_text(encoding="utf-8-sig"), filename=str(source))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert node.module not in retired, str(source)
            elif isinstance(node, ast.Import):
                assert not retired.intersection(alias.name for alias in node.names), str(source)
