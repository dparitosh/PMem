"""Apply and verify the idempotent Neo4j publication schema."""
from __future__ import annotations

import os
from pathlib import Path


SCHEMA_FILE = Path(__file__).resolve().parents[2] / "infra" / "deployment" / "neo4j-publication-index.cypher"
REQUIRED_CONSTRAINTS = {"uq_ontologyresource_identity", "uq_ontologypublication_identity", "depo_bridge_publication_id"}


def _statements(text: str) -> list[str]:
    lines = [line for line in text.splitlines() if not line.lstrip().startswith("//")]
    return [statement.strip() for statement in "\n".join(lines).split(";") if statement.strip()]


def _auth():
    mode = os.getenv("NEO4J_AUTH_MODE", "token").strip().lower()
    if mode == "none":
        return None
    if mode != "token":
        raise RuntimeError("NEO4J_AUTH_MODE must be token or none")
    user, password = os.getenv("NEO4J_USER") or os.getenv("NEO4J_USERNAME"), os.getenv("NEO4J_PASS") or os.getenv("NEO4J_PASSWORD")
    if not user or not password:
        raise RuntimeError("Neo4j credentials are required when NEO4J_AUTH_MODE=token")
    return user, password


def provision(*, check_only: bool = False) -> dict:
    from neo4j import GraphDatabase

    uri, database = os.getenv("NEO4J_URI") or os.getenv("NEO4J_URL"), os.getenv("NEO4J_DATABASE", "neo4j")
    if not uri:
        raise RuntimeError("NEO4J_URI is required")
    with GraphDatabase.driver(uri, auth=_auth(), connection_timeout=10, max_transaction_retry_time=0) as driver:
        driver.verify_connectivity()
        if not check_only:
            for statement in _statements(SCHEMA_FILE.read_text(encoding="utf-8")):
                driver.execute_query(statement, database_=database)
        records, _, _ = driver.execute_query(
            "SHOW CONSTRAINTS YIELD name WHERE name IN $names RETURN name ORDER BY name",
            names=sorted(REQUIRED_CONSTRAINTS), database_=database, routing_="r",
        )
    found = {record["name"] for record in records}
    missing = REQUIRED_CONSTRAINTS - found
    if missing:
        raise RuntimeError("Missing Neo4j publication constraints: " + ", ".join(sorted(missing)))
    return {"status": "ok", "database": database, "constraints": sorted(found)}


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(provision(check_only=args.check_only)))
    except Exception as exc:
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__, "action": "Check Neo4j connectivity, database selection and schema privileges."}))
        raise SystemExit(1) from None
