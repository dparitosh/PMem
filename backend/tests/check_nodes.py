"""Read-only Neo4j node summary using centralized configuration."""

from __future__ import annotations

from dotenv import load_dotenv

from backend.core.db_config import Neo4jConnection, get_config


def main() -> int:
    load_dotenv("backend/.env")
    cfg = get_config()
    with Neo4jConnection(database=cfg.database) as session:
        result = session.run(
            "MATCH (n) RETURN count(n) as total, collect(distinct labels(n)) as types LIMIT 1"
        )
        record = result.single()
        if record:
            print(f"Total nodes: {record['total']}")
            print(f"Node types: {record['types']}")
        else:
            print("No nodes found")

        result = session.run("MATCH (n) RETURN labels(n) as labels, n LIMIT 20")
        for record in result:
            print(f"  - {record['labels']}: {dict(record['n'])}")

        result = session.run(
            "MATCH ()-[r]-() RETURN count(r) as total, collect(distinct type(r)) as types LIMIT 1"
        )
        record = result.single()
        if record:
            print(f"Total relationships: {record['total']}")
            print(f"Rel types: {record['types']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
