# Backend Semantic Workflow Fallback

This guide is the backend-side fallback for ontology semantic workflows when you do not want to depend on the UI.

Use it for:

- linking imported instance data to a registered ontology
- generating ontology merge plans
- validating ontology registration quality
- generating dictionary and taxonomy review artifacts
- producing graph chunks for downstream review

## Preconditions

Confirm these are ready:

- Neo4j is running
- backend environment is available
- required ontology files are already registered in the app
- import task has already completed if you want to run `instance.link`

## Script

Run the repository-owned script from the DEPO installation root:

```powershell
backend\.dt_venv\Scripts\python.exe backend\scripts\run_semantic_workflow.py --help
```


## 1. Link imported instances to ontology

Dry run only, no Neo4j mutation:

```powershell
backend\.dt_venv\Scripts\python.exe backend\scripts\run_semantic_workflow.py instance-link --ontology-id plmxmlpdm_1781143225 --import-task-id 6636daef-9b03-4d97-9dbd-c085722984f4
```


Apply approved links:

```powershell
backend\.dt_venv\Scripts\python.exe backend\scripts\run_semantic_workflow.py instance-link --ontology-id plmxmlpdm_1781143225 --import-task-id 6636daef-9b03-4d97-9dbd-c085722984f4 --apply-links
```

What to review:

- `summary.candidate_count`
- `summary.selected_for_apply`
- `summary.high_confidence_candidates`
- `summary.ambiguous_candidates`
- `summary.generic_matches_filtered`
- top `result.candidates`

This workflow now prefers type-based signals and avoids auto-linking weak generic matches like `Part` unless they score strongly and unambiguously.

## 2. Generate semantic ontology merge plan

```powershell
backend\.dt_venv\Scripts\python.exe backend\scripts\run_semantic_workflow.py ontology-merge --source-ontology-id mbseout_1781143722 --target-ontology-id plmxmlpdm_1781143225
```


What to review:

- `summary.overlap_count`
- `summary.addition_count`
- `summary.conflict_count`
- `summary.subclass_gap_count`
- `conflicts`
- `subclass_gaps`

This merge plan is structure-based. It compares classes, properties, domain/range, and subclass relationships from Owlready2-backed reasoning instead of raw token overlap.

## 3. Validate ontology

```powershell
backend\.dt_venv\Scripts\python.exe backend\scripts\run_semantic_workflow.py ontology-validate --ontology-id mbseout_1781143722
```

## 4. Generate dictionary

```powershell
backend\.dt_venv\Scripts\python.exe backend\scripts\run_semantic_workflow.py dictionary-generate --ontology-id mbseout_1781143722
```

## 5. Generate taxonomy

```powershell
backend\.dt_venv\Scripts\python.exe backend\scripts\run_semantic_workflow.py taxonomy-generate --ontology-id mbseout_1781143722
```

## 6. Generate graph chunks

```powershell
backend\.dt_venv\Scripts\python.exe backend\scripts\run_semantic_workflow.py graph-chunk --ontology-id mbseout_1781143722 --chunk-size 120
```

## Optional: save output to file

```powershell
backend\.dt_venv\Scripts\python.exe backend\scripts\run_semantic_workflow.py ontology-merge --source-ontology-id mbseout_1781143722 --target-ontology-id plmxmlpdm_1781143225 --output D:\Temp\merge-plan.json
```

## Notes

- Structural import and semantic linking remain separate by design. Import first, then review and apply semantic links.
- `instance.link` only auto-applies high-confidence, non-ambiguous matches.
- The merge report is intended as a review artifact, not an automatic destructive merge.
