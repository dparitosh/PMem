"""Delete ElectronicAssembly and ComponentInstance test nodes.

This is intentionally guarded because it mutates Neo4j data. Connection
settings come from `backend/.env` through the centralized db config.
"""

from __future__ import annotations

import argparse

from dotenv import load_dotenv

from backend.core.db_config import Neo4jConnection, get_config


def delete_test_nodes() -> int:
    cfg = get_config()
    with Neo4jConnection(database=cfg.database) as session:
        before = session.run(
            """
            MATCH (n)
            WHERE n:ElectronicAssembly OR n:ComponentInstance
            RETURN count(n) AS count
            """
        ).single()["count"]
        session.run(
            """
            MATCH (m)
            WHERE m:ElectronicAssembly OR m:ComponentInstance
            DETACH DELETE m
            """
        )
    return int(before)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", default="backend/.env")
    parser.add_argument("--yes", action="store_true", help="Required for destructive cleanup.")
    args = parser.parse_args()

    if not args.yes:
        raise SystemExit("Refusing to delete Neo4j nodes without --yes.")

    load_dotenv(args.env_file)
    deleted = delete_test_nodes()
    print(f"Deleted {deleted} ElectronicAssembly/ComponentInstance nodes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
