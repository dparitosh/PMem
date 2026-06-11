#!/usr/bin/env python
"""CLI fallback for semantic ontology workflows.

Supports direct backend execution for:
- instance.link
- ontology.merge
- ontology.validate
- dictionary.generate
- taxonomy.generate
- graph.chunk
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from backend.Services.semantic_workflow_service import SemanticWorkflowService


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, default=str))


def fail(message: str, *, details: Any | None = None, code: int = 1) -> int:
    payload: dict[str, Any] = {"status": "error", "message": message}
    if details is not None:
        payload["details"] = details
    print_json(payload)
    return code


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run backend semantic workflows without the UI.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    link = subparsers.add_parser("instance-link", help="Link imported instances to a registered ontology.")
    link.add_argument("--ontology-id", required=True, help="Registered ontology id or prefix.")
    link.add_argument("--import-task-id", required=True, help="Import task id from the structural import pipeline.")
    link.add_argument("--apply-links", action="store_true", help="Write INSTANCE_OF relationships to Neo4j.")

    merge = subparsers.add_parser("ontology-merge", help="Generate a semantic merge plan between two ontologies.")
    merge.add_argument("--source-ontology-id", required=True, help="Source ontology id or prefix.")
    merge.add_argument("--target-ontology-id", required=True, help="Target ontology id or prefix.")

    validate = subparsers.add_parser("ontology-validate", help="Validate a registered ontology.")
    validate.add_argument("--ontology-id", required=True, help="Registered ontology id or prefix.")

    dictionary = subparsers.add_parser("dictionary-generate", help="Generate a review dictionary from an ontology.")
    dictionary.add_argument("--ontology-id", required=True, help="Registered ontology id or prefix.")

    taxonomy = subparsers.add_parser("taxonomy-generate", help="Generate a taxonomy artifact from an ontology.")
    taxonomy.add_argument("--ontology-id", required=True, help="Registered ontology id or prefix.")

    chunk = subparsers.add_parser("graph-chunk", help="Generate chunked ontology graph artifacts.")
    chunk.add_argument("--ontology-id", required=True, help="Registered ontology id or prefix.")
    chunk.add_argument("--chunk-size", type=int, default=80, help="Terms per chunk.")

    parser.add_argument(
        "--output",
        help="Optional path to write the workflow result JSON.",
    )
    return parser.parse_args()


def payload_for_args(args: argparse.Namespace) -> tuple[str, dict[str, Any]]:
    if args.command == "instance-link":
        return (
            "instance.link",
            {
                "ontology_id": args.ontology_id,
                "import_artifact_manifest": {"task_id": args.import_task_id},
                "apply_links": bool(args.apply_links),
            },
        )
    if args.command == "ontology-merge":
        return (
            "ontology.merge",
            {
                "source_ontology_id": args.source_ontology_id,
                "target_ontology_id": args.target_ontology_id,
            },
        )
    if args.command == "ontology-validate":
        return ("ontology.validate", {"ontology_id": args.ontology_id})
    if args.command == "dictionary-generate":
        return ("dictionary.generate", {"ontology_id": args.ontology_id})
    if args.command == "taxonomy-generate":
        return ("taxonomy.generate", {"ontology_id": args.ontology_id})
    if args.command == "graph-chunk":
        return ("graph.chunk", {"ontology_id": args.ontology_id, "chunk_size": args.chunk_size})
    raise ValueError(f"Unsupported command: {args.command}")


def write_output(path_str: str, payload: dict[str, Any]) -> None:
    path = Path(path_str).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def main() -> int:
    args = parse_args()
    workflow_id, payload = payload_for_args(args)

    try:
        result = SemanticWorkflowService.execute(workflow_id, payload)
        envelope = {
            "status": "success",
            "workflow_id": workflow_id,
            "payload": payload,
            "result": result,
        }
        print_json(envelope)
        if args.output:
            write_output(args.output, envelope)
        return 0
    except Exception as exc:
        return fail(str(exc))


if __name__ == "__main__":
    sys.exit(main())
