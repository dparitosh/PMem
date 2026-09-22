# Support tools

Run tools from the repository root using the project's Python environment.
These are operator utilities, not application startup scripts.

| Location | Purpose |
| --- | --- |
| `admin/` | Explicit maintenance operations, including destructive graph cleanup |
| `diagnostics/` | Schema, import, graph and model-runtime diagnostics |
| `import/` | Manual import/upload, task polling and commit helpers |
| `tests/` | Manual service integration checks |
| `code_graph_audit.py` | Static code dependency audit |

Inspect a tool's arguments and target configuration before execution. Several
import and test helpers target the compatibility API on port 8000 and need live
services; they are not part of default regression certification. Some helpers
need optional dependencies beyond the supported service requirements.

Use `python -m tools.admin.cleanup_neo4j --help` for the maintained graph cleanup
entry point. The redundant `scripts/_cleanup_neo4j.py` wrapper was removed.
Cleanup requires explicit confirmation in the utility; do not run it as part of
installation or automated tests.

Deployment and installation belong in `infra/`; format-conversion command-line
tools live in `scripts/` and their 3DX usage is in
[`scripts/README_3dx.md`](../scripts/README_3dx.md). Backend-specific workflow
commands remain in `backend/scripts/` because they depend on backend packages.
