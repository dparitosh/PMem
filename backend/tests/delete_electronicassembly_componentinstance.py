"""Delete Neo4j nodes by prefix or label in safe batches.

This is intentionally guarded because it mutates Neo4j data. Connection
settings come from `backend/.env` through the centralized db config.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
os.chdir(REPO_ROOT)

from backend.core.db_config import Neo4jConnection, get_config


def delete_test_nodes(prefix: str | None = None, label: str | None = None, batch_size: int = 10000) -> int:
    cfg = get_config()
    with Neo4jConnection(database=cfg.database) as session:
        if prefix:
            before = session.run(
                """
                MATCH (n)
                WHERE coalesce(n.ontology_prefix, n.prefix) = $prefix
                RETURN count(n) AS count
                """,
                {"prefix": prefix},
            ).single()["count"]
            session.run(
                f"""
                MATCH (n)
                WHERE coalesce(n.ontology_prefix, n.prefix) = $prefix
                CALL (n) {{
                    DETACH DELETE n
                }} IN TRANSACTIONS OF {batch_size} ROWS
                """,
                {"prefix": prefix},
            ).consume()
        elif label:
            before = session.run(
                f"""
                MATCH (n:`{label}`)
                RETURN count(n) AS count
                """
            ).single()["count"]
            session.run(
                f"""
                MATCH (n:`{label}`)
                CALL (n) {{
                    DETACH DELETE n
                }} IN TRANSACTIONS OF {batch_size} ROWS
                """
            ).consume()
        else:
            before = session.run(
                """
                MATCH (n)
                RETURN count(n) AS count
                """
            ).single()["count"]
            session.run(
                f"""
                MATCH (n)
                CALL (n) {{
                    DETACH DELETE n
                }} IN TRANSACTIONS OF {batch_size} ROWS
                """
            ).consume()
    return int(before)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", default="backend/.env")
    parser.add_argument("--yes", action="store_true", help="Required for destructive cleanup.")
    parser.add_argument("--prefix", help="Delete only nodes whose ontology prefix matches this value.")
    parser.add_argument("--label", help="Delete only nodes with this label.")
    parser.add_argument("--batch-size", type=int, default=10000)
    args = parser.parse_args()

    if not args.yes:
        raise SystemExit("Refusing to delete Neo4j nodes without --yes.")
    if args.prefix and args.label:
        raise SystemExit("Use either --prefix or --label, not both.")

    load_dotenv(args.env_file)
    deleted = delete_test_nodes(prefix=args.prefix, label=args.label, batch_size=args.batch_size)
    scope = f"prefix '{args.prefix}'" if args.prefix else (f"label '{args.label}'" if args.label else "all nodes")
    print(f"Deleted {deleted} nodes for {scope}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
