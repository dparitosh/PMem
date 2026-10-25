# DEPO release acceptance — 24 October 2026

## Current evidence

| Gate | Result | Scope |
|---|---|---|
| Scoped domain evidence fixtures | Passed: 43 tests in 3.49 seconds | Companion domain, accuracy, retained mappings, page context, transport boundaries, existing graph search and query safety; mocked service evidence |
| AP242 / QIF / PLMXML / MBSE fixtures | Present | Synthetic labels and versioned identities; identity/provenance preservation and abstention, not full domain semantic correctness |
| Prefix-only and dual ID/prefix isolation | Fixed and tested | Foreign/missing prefix, alias-as-ID and dangling relationship evidence rejected |
| Live frontend and core APIs | Blocked | Loopback shell requests timed out; browser navigation to http://127.0.0.1:3000/ reported ERR_CONNECTION_REFUSED |
| Backup integrity and restore drill | Not executed | User confirmed no backup exists yet; no disposable restore target has been identified |
| Customer domain answer accuracy | Unverified | No percentage or calibrated confidence claimed |

The live probe included frontend port 3000 and health endpoints on 8011, 8012, 8013, 8014, 8016, 8017 and 8019. It does not establish process state for every deployment service. Browser refusal and shell timeouts establish that live acceptance could not proceed through these access paths.

## Maintained acceptance entry points

Use existing `infra/deployment/test-depo-deployment.ps1` for deployment diagnostics, `infra/windows/test-depo-browser-session.ps1` for registered read access and `infra/windows/test-depo-release.ps1` for read-only release/schema preflight. These are connectivity/configuration gates, not proof of answer correctness. `test-depo-demo-readiness.ps1` additionally probes Ollama and is appropriate only for a configured Ollama demonstration.

Removed obsolete `backend/tests/customer_acceptance_test.py` and its collection exclusion. It used legacy port 8000, lacked the required os import, and could count a data-dictionary response as proof that a specified customer XMI was loaded without actually submitting that source. No maintained callers were found outside its own file and collection exclusion. It must not be used as customer-release evidence.

## Disposable restore drill — required evidence

1. Identify the backup timestamp, database/server versions, deployment release/commit and whether writes were quiesced across PostgreSQL, Neo4j and retained artifact stores. Independent backups from different times are not automatically a consistent recovery point.
2. Inventory the PostgreSQL backup, Neo4j backup/dump and retained upload/workflow/ontology files. Keep selected environment/credential recovery material encrypted and separately access-controlled; do not put secrets in Git or acceptance reports.
3. Verify each backup against a trusted recorded checksum and record tool/version information. Checksums establish byte integrity relative to that record, not restoration success or authenticity by themselves.
4. Provision disposable PostgreSQL and Neo4j instances and separate artifact directories. Confirm their resolved paths, database names and ports differ from the current installation. Do not run restore with existing production connection settings.
5. Restore using tools compatible with the actual database versions/edition. Preserve migration history and source identities; restore graph indexes/constraints as required by that backup format. No generic overwrite command is supplied before the backup and target are identified.
6. Point a disposable application environment at those restored stores. Validate schema in CheckOnly mode. Check source artifact hashes, retained task/receipt references, publication state, IRI/UID/UUID identity, and sampled class/subclass/property relations. Use source-specific counts and provenance, not a mixture of whole-database and selected-ontology counts.
7. Exercise read-only UI retrieval, expired-session recovery and interrupted-workflow status. Uncertain writes and graph resets must not replay automatically. Compare before/after values to a recorded source fixture; do not approve new data merely to make the drill pass.
8. Record recovery duration, data loss/recovery point, failures and limitations. Only mark this gate passed after the restore and application checks actually succeed. Remove disposable resources only under their normal approved cleanup policy.

## Live UI acceptance matrix

After deploying the same tested release to the ontology, agentic, graph and frontend components, run cases for import preview/approval/recovery; ontology selection, taxonomy and inference; AP242–QIF mapping review; graph universal search; catalog/products/pipeline evidence; quality/recommendation evidence; and Admin cleanup receipts on disposable data. Inspect evidence and source revision, not just HTTP status. Confirm unavailable services/providers, empty data, 403/429 responses and stale selections produce useful messages without retaining another principal's context.

The new domain fixtures protect transport and evidence boundaries. They do not replace a domain expert's review of mapping equivalence, engineering tolerances, requirement satisfaction or generated summaries.

## Confirmed backup blocker

The user confirmed “no backup yet.” Backup/restore acceptance is blocked until a coordinated PostgreSQL, Neo4j and retained-artifact backup set exists and a disposable restore target is identified. No backup was created or restored by this audit. Preserve the current installation; do not mark this release gate passed from code backups or unit-test results.


## Neo4j recovery evidence update — 2026-10-25

A real online full backup of local Neo4j database `neo4j` completed and was restored into isolated workspace directories as `pmem-restore-test`. The offline consistency check passed for graph, indexes, counts and property ownership. The 97,513,100-byte compressed backup and SHA256 manifest are retained locally under `C:/Users/Admin/Documents/Codex/2026-10-18/in/outputs/neo4j-recovery-20261025`. Detailed scope and limitations are in `RECOVERY-RESULT.md` there. This supersedes the earlier "no backup yet" observation for this Neo4j database only.

The full release gate remains open: no secondary DBMS startup/application query-equivalence test, authentication metadata restoration, or coordinated PostgreSQL and artifact recovery was performed. The backup excludes users/roles and is not a complete production recovery package. Live stores were not replaced or stopped.
