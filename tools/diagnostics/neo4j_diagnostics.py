"""Review Neo4j and public service health without mutating data."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

from backend.core.db_config import Neo4jConnection, get_config


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_selected_environment(env_file: str) -> Path:
    """Load the requested deployment configuration with deterministic precedence."""
    path = Path(env_file).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path = path.resolve()
    if not path.is_file():
        raise SystemExit(f"Environment file was not found: {path}")
    load_dotenv(path, override=True)
    get_config.cache_clear()
    return path


def _request(label: str, url: str) -> tuple[int | None, str]:
    try:
        response = requests.get(url, timeout=5)
        return response.status_code, response.text[:200].replace("\n", " ")
    except requests.RequestException as exc:
        return None, str(exc)


def _neo4j_summary() -> dict[str, Any]:
    cfg = get_config()
    with Neo4jConnection(database=cfg.database) as session:
        nodes = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
        rels = session.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
        labels = session.run(
            "MATCH (n) RETURN labels(n) AS labels, count(*) AS c ORDER BY c DESC LIMIT 20"
        ).data()
        rel_types = session.run(
            "MATCH ()-[r]->() RETURN type(r) AS type, count(*) AS c ORDER BY c DESC LIMIT 20"
        ).data()
    return {"nodes": nodes, "relationships": rels, "labels": labels, "relationship_types": rel_types}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-url", default=os.getenv("BACKEND_URL", "http://localhost:8000"))
    parser.add_argument("--frontend-url", default=os.getenv("FRONTEND_URL", "http://localhost:3000"))
    parser.add_argument("--env-file", default=".env.local")
    args = parser.parse_args()

    load_selected_environment(args.env_file)

    backend_url = args.backend_url.rstrip("/")
    frontend_url = args.frontend_url.rstrip("/")

    print("Service health")
    for label, url in {
        "backend openapi": f"{backend_url}/openapi.json",
        "backend ontologies": f"{backend_url}/api/v1/ontology/registered",
        "frontend": frontend_url,
    }.items():
        status, body = _request(label, url)
        print(f"  {label}: {'ERROR' if status is None else 'HTTP ' + str(status)} {body}")

    print("\nNeo4j")
    try:
        summary = _neo4j_summary()
    except Exception as exc:
        print(f"  ERROR: {exc}")
        return 1

    print(f"  nodes: {summary['nodes']}")
    print(f"  relationships: {summary['relationships']}")
    print("  labels:")
    for row in summary["labels"]:
        print(f"    {row['labels']}: {row['c']}")
    print("  relationship types:")
    for row in summary["relationship_types"]:
        print(f"    {row['type']}: {row['c']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
