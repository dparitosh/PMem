# Local recovery qualification — 29 October 2026

## Confirmed result

PostgreSQL 16.15 backup and restore passed against a new, isolated local cluster. The live `depo` database was not replaced, its role permissions were not elevated, and no application credentials were rotated.

The drill held a read-only repeatable-read transaction, exported its snapshot to `pg_dump`, then compared every restored user table against that same snapshot. This avoids comparing a backup to a later, potentially changing live database.

| Check | Result |
| --- | --- |
| Application tables | 10 |
| Rows | 384 |
| Table contents | All counts and sorted row fingerprints matched |
| Restored constraints | 25 |
| Custom-format backup | 5,993,545 bytes |
| Backup SHA-256 | `0a5128b1e644796eeb5b36fdd00e7940a2364a044f47394ad581826e0e8ee4b9` |
| Disposable server | Bound to loopback, SCRAM authentication; stopped after validation |

Private backup, diagnostic logs and machine-readable result are retained outside the repository under `outputs/postgres-recovery-20261029` in the task workspace. The directory has restricted Windows permissions. The temporary password file was removed. Database contents and credentials are not included in this report.

## Graph recovery evidence

The earlier 25 October local graph drill created a 97,513,100-byte online backup and restored it into separate directories. Its offline graph/index/count/property-ownership consistency check passed. Backup SHA-256: `7A03D40023204CC4A7B3F400F36FDEAEC93DFEAA2BF726AFB02E9FA482017F00`.

See the historical recovery entry in [release acceptance](../architecture-review-2026-10-24/DEPO_RELEASE_ACCEPTANCE.md). That drill did not start a secondary database server or demonstrate application query equivalence; user/role metadata was excluded.

## Remaining release gates

- A coordinated application recovery point covering PostgreSQL, graph publication receipts and retained ontology/import artifacts. Independent database backups do not establish cross-store consistency.
- Start a restored graph in an isolated server and verify representative publication, traversal and source-identity queries.
- Restore retained files and verify registry references, artifact hashes and governed workflow recovery against restored stores.
- Repeat recovery and browser acceptance on the customer Windows deployment, including gateway/session routing and supervisor crash/reboot recovery.
- Qualify live model responses separately. No LLM was called during this drill.

These results improve local recovery evidence; they do not constitute customer release acceptance.

## Follow-up: retained ontology recovery audit

The follow-up read the configured `semantic.depo_registry` records under namespace `ontology_catalog` without changing them. Both current catalog ontologies had accessible content-addressed files and catalog mirrors. Both mirrors matched their content hashes. Isolated copies were created in the restricted recovery directory and rehashed successfully: 21,205,084 bytes and 1,914,885 bytes, 23,119,969 bytes total.

The earlier graph backup was rehashed and still matched its recorded SHA-256. These checks confirm file integrity and recoverable copies for the two current ontology artifacts. They do not cover all import uploads or establish a coordinated point in time across stores. The running database was not restored or reset.
