# Backend Import Fallback

This guide is the supported fallback when the UI import pipeline is slow, times out, or does not complete cleanly for large files.

It uses the same backend import service and the same API stages as the UI:

1. upload
2. preview
3. commit
4. poll status
5. verify in Neo4j

## When to use this path

Use this fallback when:

- a large `PLMXML`, `XML`, `STEP`, or `STPX` file stalls in the UI
- the progress bar stays in `Writing relationships...` for too long
- the browser tab is unstable but backend services are healthy
- you need a deterministic run log before customer delivery

## Preconditions

Confirm these are running:

- Neo4j
- backend API on `http://localhost:8000`
- frontend on `http://localhost:3000` if you also want to inspect the UI

Quick health check:

```powershell
Invoke-RestMethod -Uri http://localhost:8000/health
Invoke-RestMethod -Uri http://localhost:8000/graph-metrics
```

## Optional: clean Neo4j first

Use the Admin page button if available.

Or verify the graph is already empty:

```powershell
Invoke-RestMethod -Uri http://localhost:8000/graph-metrics | ConvertTo-Json -Depth 5
```

Expected clean result:

```json
{
  "total_nodes": 0,
  "total_relationships": 0
}
```

## Fallback import flow

Example file:

`D:\Download\003257_cad-JuicePurification-InductionMotor.xml`

## Preferred CLI wrapper

Use the reusable script first:

```powershell
backend\.dt_venv\Scripts\python.exe backend\scripts\import_file.py "D:\Download\003257_cad-JuicePurification-InductionMotor.xml"
```

Clean Neo4j first when needed:

```powershell
backend\.dt_venv\Scripts\python.exe backend\scripts\import_file.py "D:\Download\003257_cad-JuicePurification-InductionMotor.xml" --clean-first
```

Preview only:

```powershell
backend\.dt_venv\Scripts\python.exe backend\scripts\import_file.py "D:\Download\003257_cad-JuicePurification-InductionMotor.xml" --skip-commit
```

The script prints:

- upload response
- preview status
- pre-commit summary
- commit completion status
- final Neo4j verification by `import_id`

Run this exact Python command from the repo root:

```powershell
backend\.dt_venv\Scripts\python.exe -c "import json, time, requests; from pathlib import Path; file_path=Path(r'D:/Download/003257_cad-JuicePurification-InductionMotor.xml'); files={'file': (file_path.name, file_path.read_bytes(), 'application/xml')}; upload=requests.post('http://localhost:8000/api/v1/import/upload', files=files, timeout=120); upload.raise_for_status(); task_id=upload.json()['task_id']; print(json.dumps({'phase':'upload','task_id':task_id}, indent=2)); preview_ready=False; \
for _ in range(180): \
    status=requests.get(f'http://localhost:8000/api/v1/import/status/{task_id}', timeout=60); status.raise_for_status(); payload=status.json(); \
    if payload.get('current_stage')=='preview' or int(payload.get('progress', 0)) >= 75: \
        print(json.dumps({'phase':'preview-status','status':payload}, indent=2)); preview_ready=True; break; \
    time.sleep(1); \
assert preview_ready, 'Preview stage did not complete in time'; \
pre=requests.get(f'http://localhost:8000/api/v1/import/pre-commit/{task_id}', timeout=120); pre.raise_for_status(); print(json.dumps({'phase':'pre-commit','preview':pre.json()}, indent=2)); \
commit=requests.post(f'http://localhost:8000/api/v1/import/commit/{task_id}', timeout=120); commit.raise_for_status(); print(json.dumps({'phase':'commit-queued','commit':commit.json()}, indent=2)); \
for _ in range(300): \
    status=requests.get(f'http://localhost:8000/api/v1/import/status/{task_id}', timeout=60); status.raise_for_status(); payload=status.json(); \
    if payload.get('status') == 'completed' and not payload.get('committing'): \
        print(json.dumps({'phase':'completed','status':payload}, indent=2)); break; \
    if payload.get('status') == 'failed': \
        raise RuntimeError(json.dumps(payload, indent=2)); \
    time.sleep(2)"
```

## What to look for in the result

In the final status payload, check:

- `status = completed`
- `commit_metrics.nodes_written`
- `commit_metrics.relationships_written`
- `commit_metrics.relationships_skipped`
- `result.unresolved_references`
- `result.errors`

Release-quality target:

- `relationships_skipped = 0`
- `unresolved_references = 0`
- `errors = []`

## Neo4j verification after import

Replace the task id with the one returned by the import run.

Node count:

```powershell
backend\.dt_venv\Scripts\python.exe -c "from backend.core.graph import query_with_timeout; import json; print(json.dumps(query_with_timeout(\"MATCH (n {import_id: $task_id}) RETURN count(n) AS c\", {'task_id':'<TASK_ID>'})))"
```

Relationship count:

```powershell
backend\.dt_venv\Scripts\python.exe -c "from backend.core.graph import query_with_timeout; import json; print(json.dumps(query_with_timeout(\"MATCH (a {import_id: $task_id})-[r]->(b {import_id: $task_id}) RETURN count(r) AS c\", {'task_id':'<TASK_ID>'})))"
```

Top relationship types:

```powershell
backend\.dt_venv\Scripts\python.exe -c "from backend.core.graph import query_with_timeout; import json; print(json.dumps(query_with_timeout(\"MATCH (a {import_id: $task_id})-[r]->(b {import_id: $task_id}) RETURN type(r) AS type, count(r) AS count ORDER BY count DESC LIMIT 20\", {'task_id':'<TASK_ID>'}), indent=2))"
```

Overall graph metrics:

```powershell
Invoke-RestMethod -Uri http://localhost:8000/graph-metrics | ConvertTo-Json -Depth 5
```

## Latest validated XML result

Validated in this repository for:

`D:\Download\003257_cad-JuicePurification-InductionMotor.xml`

Observed result:

- nodes: `7206`
- relationships: `9628`
- skipped relationships: `0`
- unresolved references: `0`

## UI review checklist

After backend import completes, review these surfaces in the UI.

### Import page

Workflow:

- `Import instance graph`

Check:

- step progression advances through all four pipeline stages
- file row changes from upload to preview to load/verify cleanly
- `Load to Neo4j` appears only after parse/preview is ready
- final counts in the row match backend task metrics
- no stale status remains after completion

### Graph Explorer

Check both modes:

- `Ontology schema`
- `Contextual graph`

Check:

- search returns stable results and does not reset on small mouse movement
- clear search returns to the active graph scope, not an unrelated graph
- relationship lines and arrows remain readable on dense views
- ontology scope filter and contextual view switch do not overflow the toolbar
- large graph views show condensed labels until scoped or searched

### Ontology flow

If the import is structural only:

- use `Link instances to ontology` after import
- select the imported graph output and a registered ontology
- review mapping candidates before applying semantic links

## Where task snapshots are stored

Import task snapshots are written here:

`D:\Githuv_repo\PMem\uploads\.import_tasks`

Useful files:

- `<task_id>.json`
- `<task_id>.json.parsed_rows.json`

These help when the browser or API caller loses the live task state but the backend completed the work.

## Notes

- `GeneralRelation` and `RequirementRevision` identities are now preserved in the import rows, so trace links from PLMXML are retained instead of being dropped during flattening.
- For instance data, structural import and ontology linking are intentionally separated. Import first, then use semantic bridge for ontology alignment.
