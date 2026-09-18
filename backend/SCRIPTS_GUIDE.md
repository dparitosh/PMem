# Backend Scripts Guide

This guide separates the Python entry points that are safe and repeatable from the
one-off utilities and test-only helpers scattered through the backend.

## What is standardized

These are the most usable command-line entry points in the repo:

### `backend/scripts/import_file.py`

Submit one source file through the same governed ingestion path as the UI.
The command retains an immutable artifact and starts an approved data job; it
does not clean or publish the graph.

Typical use:

```powershell
python backend/scripts/import_file.py <file_path> --base-url http://127.0.0.1:8014
```

Useful flags:
- `--profile <profile-id|auto>`
- `--job-id <approved-job-id>` and `--job-version <semver>`
- `--source-system <name>`
- `--request-timeout <seconds>`

Best for:
- PLMXML, XML, STEP, XMI, JSON, CSV, Excel imports
- reproducing the governed UI import submission from the command line

---

### `backend/scripts/run_semantic_workflow.py`

Run semantic workflows directly from the command line.

Available subcommands:
- `instance-link`
- `ontology-merge`
- `ontology-validate`
- `dictionary-generate`
- `taxonomy-generate`
- `graph-chunk`

Examples:

```powershell
python backend/scripts/run_semantic_workflow.py instance-link --ontology-id <id> --import-task-id <task-id>
python backend/scripts/run_semantic_workflow.py ontology-validate --ontology-id <id>
python backend/scripts/run_semantic_workflow.py ontology-merge --source-ontology-id <source> --target-ontology-id <target>
```

Best for:
- semantic bridge alignment
- ontology review and validation
- taxonomy and graph artifact generation

## Utility scripts

These scripts are usable, but they are not packaged as polished operator tools.

### `backend/Services/owl_xsd_engine.py`

XSD to OWL/TTL conversion utilities.

Best for:
- schema-to-ontology generation
- AP242 / PLMXML-style schema conversion

### `backend/Services/owl_xmi_engine.py`

XMI to OWL/Turtle conversion utility.

Typical form:

```powershell
python backend/Services/owl_xmi_engine.py <xmi_file> <output_file> [--base-uri <uri>] [--title <text>]
```

### `backend/Services/step_0_generate_ontology.py`

Legacy ontology generation helper for PLMXML-oriented input.

Typical form:

```powershell
python backend/Services/step_0_generate_ontology.py <plmxml_file>
```

### `backend/Services/graph_embeddings.py`

Graph embedding and similarity support.

Best for:
- context-aware graph embeddings
- ontology / node similarity workflows

## Test-only and admin helpers

These are useful when debugging or cleaning data, but they should be treated as
maintenance scripts, not everyday workflows.

- `backend/tests/clean_neo4j_schema.py`
- `backend/tests/check_nodes.py`
- `backend/tests/delete_electronicassembly_componentinstance.py`
- `backend/tests/integration_test.py`
- `backend/tests/customer_acceptance_test.py`
- `backend/tests/test_*.py`

### Destructive cleanup

`backend/tests/delete_electronicassembly_componentinstance.py` is destructive.
It requires `--yes` and supports:

- `--prefix`
- `--label`
- `--batch-size`

Use this only when you intend to remove data.

## What is not standardized

The repo also contains Python modules under `backend/Services/` that are primarily
application services. Some have standalone `main()` entry points, but they are not
all consistent in:

- argument naming
- help text
- exit codes
- logging
- output format

In other words: **some scripts are ready to use; the whole Python surface is not yet standardized**.

## Recommended operator flow

1. Use `backend/scripts/import_file.py` for imports.
2. Use `backend/scripts/run_semantic_workflow.py` for semantic bridge operations.
3. Use the `Services/*` utilities only when you need conversion or graph helper behavior.
4. Use `backend/tests/*` only for validation, cleanup, or troubleshooting.

## Notes

- Prefer running commands from the repository root.
- Keep Neo4j, backend, and frontend versions aligned before testing workflows.
- For destructive cleanup or schema reset, take a backup first.

