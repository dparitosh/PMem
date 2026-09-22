# PostgreSQL application tables and columns

The authoritative DDL is [`backend/postgres_migrations.py`](../../backend/postgres_migrations.py).
Do not maintain a second manual table-creation SQL script. Versions 1-4 are
applied in ascending order inside a transaction protected by an advisory lock.
The schema name is `DEPO_DATABASE_SCHEMA` (default `semantic`).

| Relation | Columns and PostgreSQL types | Constraints/defaults |
| --- | --- | --- |
| `depo_schema_migrations` | `version integer`, `name text`, `applied_at timestamptz` | PK `version`; timestamp defaults to `now()` |
| `depo_registry` | `namespace text`, `key text`, `value jsonb`, `updated_at timestamptz` | PK `(namespace,key)`; timestamp defaults to `now()` |
| `depo_runtime_state` | `kind text`, `key text`, `value jsonb`, `updated_at double precision` | PK `(kind,key)`; caller supplies epoch timestamp |
| `depo_chat_messages` | `session_id text`, `message_id bigserial`, `role text`, `content text`, `created_at double precision` | PK `message_id`; index `(session_id,message_id)`; caller supplies epoch timestamp |
| `depo_rate_limits` | `client_key text`, `created_at double precision` | Index `(client_key,created_at)`; no primary key |
| `depo_metadata_assets` | `asset_id text`, `revision integer`, `value jsonb`, `updated_at timestamptz` | PK `asset_id`; revision > 0; JSON must be an object; timestamp defaults to `now()` |
| `depo_metadata_events` | `event_id text`, `asset_id text`, `revision integer`, `value jsonb`, `created_at timestamptz` | PK `event_id`; FK to assets; unique `(asset_id,revision)`; JSON object check; timestamp defaults to `now()` |
| `depo_metadata_outbox` | `event_id text`, `status text`, `created_at timestamptz` | PK/FK to events; status `pending` or `published`, default `pending`; timestamp defaults to `now()`; partial index for pending records |

All table columns above are NOT NULL (including primary keys). `bigserial`
creates a bigint column with an owned sequence. The current migration does not
add a positive-revision check to `depo_metadata_events`; do not assume it exists.

The `depo_ontology_analytics` **view** projects `depo_registry` entries in namespace
`ontology_catalog`. Text columns: `ontology_id`, `ontology_name`, `lifecycle_status`,
`semantic_completeness`, `schema_set_digest`, `analytics_profile_artifact_id`.
Numeric columns: `triples`, `classes`, `object_properties`, `datatype_properties`.
Missing JSON fields may produce NULL view values. It is not a writable base table.

Bridge jobs, agentic workflow runs, catalog records and other control-plane
documents share `depo_registry` through namespaces. Their JSON properties are
not separate SQL columns. No per-service or per-candidate tables must be created.

## Initialize or upgrade

Provision the database/login/schema first using [PostgreSQL provisioning](README.md),
install backend dependencies, and configure root `.env.local`. Back up existing
customer data before an upgrade. With the database already running:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\deployment\invoke-depo-lifecycle.ps1 -Action InitializeDatabase -EnvFile .env.local
if ($LASTEXITCODE -ne 0) { throw 'Migration or schema verification failed.' }
```

This applies pending migrations and checks 8 tables plus 1 view, all 40 column
names/types, and recorded migration versions. It does not create the PostgreSQL
server, login or database, and does not erase data. Start and ReleasePreflight
also run this migration/verification step. A check failure stops startup; do not
drop/recreate tables or edit migration history to conceal a mismatch.

To verify an existing schema without DDL or data writes:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\infra\windows\initialize-depo-schema.ps1 -EnvFile .env.local -CheckOnly
if ($LASTEXITCODE -ne 0) { throw 'Schema verification failed.' }
```

For DBA inspection, run `\dt semantic.*`, `\dv semantic.*` and
`\d+ semantic.depo_registry` in authenticated `psql`, substituting the configured
schema. The automated check verifies names/types and migration history, not all
privileges, constraints, index definitions or customer data. Inspect those and
perform a backup/restore drill as part of release acceptance. Downgrade/rollback
requires the agreed backup recovery procedure; there is no automatic down migration.
