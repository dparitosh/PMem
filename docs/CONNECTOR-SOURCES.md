# Registered source acquisition

Admin → Data sources shows the 17 Semantica ingestor classes. REST and 13 additional adapters use registered acquisition workflows. File, XML and Ontology retain their existing import workflows.

## Operator setup

1. Install PMem normally. Keep the existing semantic runtime; do not copy dependencies into every service environment.
2. For optional SDKs, prepare an operator-reviewed lock containing exact `package==version --hash=sha256:<digest>` lines for the complete dependency closure. Stop PMem services and run `infra/windows/install-depo-connectors.ps1 -EnvFile .env.local -LockFile <reviewed-lock.txt>`. Use `-CheckOnly` to validate without installing. No unpinned vendor SDKs are installed automatically.
3. Configure `DEPO_CONNECTOR_PROFILES` in the selected environment file. Profiles map resource aliases to server-owned locations. Configure the referenced `DEPO_CONNECTOR_SECRET_*` variable as JSON. Keep credentials out of Git, browser fields and job payloads.
4. Restart using the normal lifecycle command. In Admin → Data sources choose a connection profile and resource, then register a named source using data-job approval access.
5. Create and approve a Data Flow job definition with job type `registered-source-ingest`, input contract `registered-connector-source-v1` and output contract `connector-records-v1`. Select that approved job in Admin and acquire the source using data-job execution access.
6. Follow the retained run to Data Flow. Acquisition retains source evidence; it does not validate business semantics, publish graph data or approve a product.

Example non-secret profile (one JSON line in the environment file):

```json
{"parts-profile":{"name":"Parts files","kind":"Parquet","resources":{"parts":"parts.parquet"},"connection_ref":"DEPO_CONNECTOR_SECRET_PARTS"}}
```

The referenced variable can contain `{"root":"D:/approved-source-data"}` for local files. Actual credentials belong only in the deployment environment or the site's protected secret provisioning process. The browser sees profile names, kinds and aliases, never locations or connection settings. A changed profile invalidates its previous registered source; register a new version. Credential rotation at the same reference does not alter the source identity.

## Adapter contracts

| Kind | Resource and supported read | Runtime requirement / server settings |
|---|---|---|
| Parquet | One file under configured root | PyArrow; `root` |
| Arrow | One Arrow file under root | PyArrow; `root` |
| Web | One allowed HTTP(S) URL | Web ingestor parser dependencies |
| Feed | One allowed feed URL | Feed ingestor dependencies |
| PublicAPI | One public GET URL | PublicAPI ingestor; public GET only |
| DB | One table identifier | SQLAlchemy and database driver; `connection_string`; read-only DB account required |
| Databricks | One table in configured catalog/schema | Databricks connector SDK; host/token/http_path/catalog/schema settings |
| Snowflake | One table in configured database/schema | Snowflake connector SDK; account/user/warehouse/database/schema and authentication settings |
| Email | One IMAP mailbox | IMAP TLS port 993; server/username/password; read-only selection and BODY.PEEK fetch |
| MCP | One resource URI | MCP SDK; configured HTTP(S) URL and optional headers; resource reads only, no tool calls |
| Repo | One allowed repository URL | Git executable and repository ingestor dependencies; shallow clone, no history |
| CloudStorage | One object key | S3/GCS/Azure SDK; provider, bucket and dedicated credentials settings |
| Stream | One Kafka topic snapshot | Kafka client; bootstrap_servers and allowed consumer security settings; no offset commits |

Web, Feed, PublicAPI, Repo and MCP use the existing outbound endpoint policy (`DEPO_REST_ALLOWED_HOSTS` where applicable). Private/loopback URLs are not enabled by this UI. REST remains the adapter for authenticated HTTP(S) APIs. Other vendor connection settings are operator-owned and should use read-only source accounts and network restrictions.

## Limits, recovery and storage

Acquisition runs in a durable pipeline worker, with SDK work in a bounded semantic-runtime child. Limits are 45 seconds, 1,000 records and 2 MiB retained output. The child monitors a 512 MiB RSS budget and a 32 MiB/5,000-file scratch budget; these are operational bounds, not an OS security sandbox. Kafka snapshots stop after 10 seconds. SDKs may buffer data before returning, so source-side limits and read-only accounts remain necessary.

Registrations and submission receipts use existing PostgreSQL registry namespaces `connector_sources` and `connector_submissions`; no extra database or sharding is introduced. Source artifacts use the existing artifact store and retention policy. Credentials are not persisted in these records.

A submission reference survives reconnects in browser storage without credentials. Check retained status first after a lost acknowledgement. Recover the same submission reference to reconcile enqueueing; only prepare a new acquisition after a verified terminal state. Concurrent tabs reconcile to one active source/job run. A later acquisition may read changed source data; its new artifact is a new snapshot.

## Verification boundary

Local tests execute actual Parquet, Arrow and disposable SQLite reads, including a real acquisition child. All 13 adapters have dispatch/limit contract coverage. Vendor/cloud/mail/MCP/Kafka accounts have not been configured or accepted in the customer deployment. A class being present, or a profile having settings, is not proof of source connectivity. Test each intended customer connection before release.
