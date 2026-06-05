"""Destructive Neo4j cleanup utility.

This tool is intentionally not imported by the API. It requires --yes and can
optionally remove runtime upload folders after wiping the graph.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from dotenv import load_dotenv

from backend.core.db_config import Neo4jConnection, get_config


def wipe_neo4j(batch_size: int) -> None:
    cfg = get_config()
    with Neo4jConnection(database=cfg.database) as session:
        before = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
        print(f"Nodes before: {before}")
        while True:
            deleted = session.run(
                "MATCH (n) WITH n LIMIT $limit DETACH DELETE n RETURN count(*) AS c",
                limit=batch_size,
            ).single()["c"]
            print(f"Deleted batch: {deleted}")
            if deleted == 0:
                break

        for row in session.run('SHOW INDEXES YIELD name, type WHERE type <> "LOOKUP"').data():
            session.run(f"DROP INDEX `{row['name']}` IF EXISTS")
            print(f"Dropped index: {row['name']}")

        for row in session.run("SHOW CONSTRAINTS YIELD name").data():
            session.run(f"DROP CONSTRAINT `{row['name']}` IF EXISTS")
            print(f"Dropped constraint: {row['name']}")

        after = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
        print(f"Nodes after: {after}")


def cleanup_uploads(upload_dir: Path, keep: set[str]) -> None:
    if not upload_dir.exists():
        print(f"Upload directory does not exist: {upload_dir}")
        return
    for child in upload_dir.iterdir():
        if not child.is_dir() or child.name in keep:
            continue
        shutil.rmtree(child)
        print(f"Removed upload folder: {child}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", default="backend/.env")
    parser.add_argument("--batch-size", type=int, default=5000)
    parser.add_argument("--delete-uploads", action="store_true")
    parser.add_argument("--upload-dir", type=Path, default=Path("ontology_uploads"))
    parser.add_argument("--keep-upload", action="append", default=[])
    parser.add_argument("--yes", action="store_true", help="Required for destructive cleanup.")
    args = parser.parse_args()

    if not args.yes:
        raise SystemExit("Refusing to perform destructive cleanup without --yes.")

    load_dotenv(args.env_file)
    wipe_neo4j(args.batch_size)
    if args.delete_uploads:
        cleanup_uploads(args.upload_dir, set(args.keep_upload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

