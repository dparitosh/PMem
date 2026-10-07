# DEPO Environment Configuration Reference

Complete installation variable reference
7 October 2026

This corrected reference covers 209 distinct configuration variables from the supplied installation configuration, the workspace .env.local, deployment, Spark, frontend and standalone examples, plus supported per-profile and service-routing variables. Every inventoried variable has an individual entry. Credential values from the supplied files are never reproduced.

## Coverage and configuration precedence

The previous edition covered only the 16 active variables in the workspace .env.local. This edition also covers the much larger installation configuration pasted into this conversation, including commented optional assignments. These are distinct sources; the contents of the running VM environment file have not been inspected directly.

Windows launchers read the selected environment file and inject values into child processes. Unified routing derives service and browser endpoints. Frontend configuration has its own build/runtime handling. The Spark example must be merged deliberately and the standalone example belongs to a separate component. Not every listed variable belongs in every installation.

Examples are template examples, not proof of an applied value or a code default. Blank means the template leaves the setting empty. Replace angle-bracket placeholders before use. Secrets are redacted even when a template supplies a placeholder. Restart affected processes after server configuration changes.

## Coverage inventory

- .env.local: 16 distinct variable names covered.

- pasted installation configuration: 107 distinct variable names covered.

- config\deployment.env.example: 106 distinct variable names covered.

- config\spark.env.example: 15 distinct variable names covered.

- frontend\.env.example: 19 distinct variable names covered.

- standalone\ontology_agentic_service\.env.example: 20 distinct variable names covered.

Additional entries expand all 17 credential profiles into actor and expiry overrides, all ten service API/browser/gateway routes, and the optional dedicated memory database setting.

## Neo4j graph configuration

### AURA_INSTANCEID

No runtime consumer was found in the reviewed backend, tools or deployment scripts. Treat this as operator metadata; it does not select a database or establish a connection.

Example: AURA_INSTANCEID=<instance identifier>

Source: .env.local

### AURA_INSTANCENAME

No runtime consumer was found in the reviewed backend, tools or deployment scripts. This label does not replace NEO4J_URI or NEO4J_DATABASE.

Example: AURA_INSTANCENAME=<instance label>

Source: .env.local

### GRAPH_PUBLICATION_TIMEOUT_SECONDS

Maximum duration of a canonical graph publication request in seconds. Deployment example 180. Independent from the overall agent workflow deadline.

Example: GRAPH_PUBLICATION_TIMEOUT_SECONDS=180

Source: pasted installation configuration; config\deployment.env.example

### NEO4J_AUTH_MODE

token uses the Neo4j username and password. none is limited to deliberately unauthenticated on-premises bolt:// or neo4j:// deployments with compatible non-TLS settings.

Example: NEO4J_AUTH_MODE=token

Source: pasted installation configuration; config\deployment.env.example

### NEO4J_DATABASE

Selects the database used by driver sessions. The code defaults to neo4j when omitted. The configured account must have access to the chosen database.

Example: NEO4J_DATABASE=ontology

Source: .env.local; pasted installation configuration; config\deployment.env.example

### NEO4J_ENCRYPTED

Boolean graph transport encryption setting. Keep it compatible with the Neo4j URI scheme and TLS policy; secure URI schemes already express transport security.

Example: NEO4J_ENCRYPTED=true

Source: pasted installation configuration; config\deployment.env.example

### NEO4J_PASS

Secret for NEO4J_USER. Retain it only in server configuration or an approved secret store. Do not import it into the PostgreSQL application credential profiles.

Example: NEO4J_PASS=<secret; never published>

Source: .env.local; pasted installation configuration; config\deployment.env.example

### NEO4J_TLS_MODE

TLS policy for the graph connection. Production example required; deliberately non-TLS private deployments use disabled. Align policy with URI scheme, encryption and certificate verification.

Example: NEO4J_TLS_MODE=required

Source: pasted installation configuration; config\deployment.env.example

### NEO4J_TLS_VERIFY

Boolean TLS certificate verification setting. Production example true. Disabling verification weakens server identity checks and must match the chosen deployment policy.

Example: NEO4J_TLS_VERIFY=true

Source: pasted installation configuration; config\deployment.env.example

### NEO4J_URI

Graph services and legacy chat connect to this address. Use an explicit supported Neo4j or Bolt URI. TLS requirements also depend on NEO4J_TLS_MODE and encryption settings. Loopback addresses refer to the application VM itself.

Example: NEO4J_URI=neo4j+s://<neo4j-host>

Source: .env.local; pasted installation configuration; config\deployment.env.example

### NEO4J_USER

Account used by the graph driver. Grant only the permissions needed by enabled read and publication operations. This is a database login, not an application API key.

Example: NEO4J_USER=depo_graph

Source: .env.local; pasted installation configuration; config\deployment.env.example

## Model providers

### EMBED_MODEL_NAME

Ollama embedding-model selector for legacy retrieval. Defaults to nomic-embed-text:latest. This is independent of the generation model; the model must support embedding requests.

Example: EMBED_MODEL_NAME=nomic-embed-text:latest

Source: .env.local; pasted installation configuration; config\deployment.env.example

### LLM_MODEL_NAME

Exact installed generation-model name including its tag. Fallback order is LLM_MODEL_NAME, OLLAMA_MODEL, then llama3:latest. The agentic health check verifies availability through /api/tags. The application does not install the model automatically.

Example: LLM_MODEL_NAME=llama3:latest

Source: .env.local; pasted installation configuration; config\deployment.env.example

### LLM_REQUEST_TIMEOUT_SECONDS

Ollama request timeout in seconds, accepted range 1–120, default 30. Provider reachability and installed models must be checked separately.

Example: LLM_REQUEST_TIMEOUT_SECONDS=30

Source: pasted installation configuration; config\deployment.env.example

### OLLAMA_API_KEY

Optional server-side secret for an authenticated Ollama gateway or proxy. A local unauthenticated daemon can leave it blank. It is not a DEPO application profile and is not imported by the application credential script.

Example: OLLAMA_API_KEY=<secret; never published>

Source: .env.local; pasted installation configuration; config\deployment.env.example

### OLLAMA_API_KEY_HEADER

Supported names are api-key, Ocp-Apim-Subscription-Key and Authorization. Defaults to api-key when a key is present. Authorization adds the Bearer prefix. Match the gateway contract; an incorrect header can cause 401 or 403.

Example: OLLAMA_API_KEY_HEADER=api-key

Source: .env.local; pasted installation configuration; config\deployment.env.example

### OLLAMA_API_URL

Alternative to OLLAMA_BASE_URL. Accepts a root or native operation URL. Direct generation preserves /api/chat or /api/generate selection; LangChain clients use the normalized root. Supplying inconsistent roots causes a configuration error.

Example: OLLAMA_API_URL=http://ollama-server:11434/api/chat

Source: .env.local; pasted installation configuration; config\deployment.env.example

### OLLAMA_BASE_URL

HTTP or HTTPS address reachable from the application VM. Defaults to http://127.0.0.1:11434. It must not contain credentials, query parameters or fragments. If OLLAMA_API_URL is also supplied, both must normalize to the same root.

Example: OLLAMA_BASE_URL=http://127.0.0.1:11434

Source: .env.local; pasted installation configuration; config\deployment.env.example

### OLLAMA_CHAT_API_URL

Optional separate native Ollama chat root or /api/chat endpoint for tool-calling workflows. A generate-only route may support summaries while lacking chat capability.

Example: OLLAMA_CHAT_API_URL=

Source: pasted installation configuration; config\deployment.env.example

### USE_EMBEDDER

Legacy retrieval and vector-chain provider selector. Accepts ollama or azure; when absent it follows USE_LLM. Selecting Ollama requires the embedding model to be installed. Enabling embeddings does not publish a data product.

Example: USE_EMBEDDER=ollama

Source: .env.local

### USE_LLM

Provider selector, not a true or false flag. Legacy model factories accept ollama or azure. The offline agentic service uses Ollama and reports not_selected for other providers. Azure additionally requires its endpoint, deployment, version and key settings.

Example: USE_LLM=ollama

Source: .env.local; pasted installation configuration; config\deployment.env.example

## Agents sessions and ontology processing

### AGENTIC_MAX_UPLOAD_BYTES

Agentic upload size limit in bytes. Example 26214400 is 25 MiB. Coordinate with proxy request limits.

Example: AGENTIC_MAX_UPLOAD_BYTES=26214400

Source: pasted installation configuration; config\deployment.env.example

### AGENTIC_RUN_TIMEOUT_SECONDS

Overall multi-step workflow deadline in seconds. Example 300. Pause, resume and recovery do not extend the original deadline; cancellation takes effect at tool boundaries.

Example: AGENTIC_RUN_TIMEOUT_SECONDS=300

Source: pasted installation configuration; config\deployment.env.example

### AGENTIC_TOOL_TIMEOUT_SECONDS

Per-tool execution timeout in seconds. Deployment example 30. It is separate from the fixed workflow execution deadline.

Example: AGENTIC_TOOL_TIMEOUT_SECONDS=30

Source: pasted installation configuration; config\deployment.env.example

### AGENT_FAILURE_RATE_ALERT_THRESHOLD

Failure-rate threshold for telemetry alerts, example 0.2 means 20 percent. This controls alerting, not execution retry policy.

Example: AGENT_FAILURE_RATE_ALERT_THRESHOLD=0.2

Source: pasted installation configuration; config\deployment.env.example

### AGENT_MEMORY_ENABLED

Enables optional Neo4j conversation and approved-mapping memory. Requires configured graph connectivity and a deliberate customer/project scope.

Example: AGENT_MEMORY_ENABLED=false

Source: pasted installation configuration; config\deployment.env.example

### AGENT_MEMORY_NEO4J_DATABASE

Optional dedicated Neo4j database for memory. Falls back to NEO4J_DATABASE when unset.

Example: AGENT_MEMORY_NEO4J_DATABASE=Not specified in supplied examples

Source: backend/Services/agent_memory_service.py

### AGENT_MEMORY_QUERY_TIMEOUT

Neo4j memory query timeout in seconds, default 5; runtime clamps it to 1–30.

Example: AGENT_MEMORY_QUERY_TIMEOUT=5

Source: pasted installation configuration; config\deployment.env.example

### AGENT_MEMORY_RETENTION_DAYS

Memory retention duration in days. Deployment default 30; configuration validation accepts 1–3650. Retention policy and actual cleanup execution are separate concerns.

Example: AGENT_MEMORY_RETENTION_DAYS=30

Source: pasted installation configuration; config\deployment.env.example

### AGENT_MEMORY_SCOPE

Unique memory isolation scope, typically customer-id:project-id. Required when memory is enabled.

Example: AGENT_MEMORY_SCOPE=<customer-id>:<project-id>

Source: pasted installation configuration; config\deployment.env.example

### AGENT_PROMPT_VERSION

Prompt revision label recorded in telemetry, example 1. Updating this label does not itself change prompt implementation.

Example: AGENT_PROMPT_VERSION=1

Source: pasted installation configuration; config\deployment.env.example

### AGENT_SESSION_IDLE_SECONDS

Companion session idle lifetime in seconds, example 1800. Independent from delegated browser credential expiry.

Example: AGENT_SESSION_IDLE_SECONDS=1800

Source: pasted installation configuration; config\deployment.env.example

### AGENT_SESSION_MAX_SECONDS

Fixed maximum companion session lifetime in seconds, example 86400. Activity does not extend this maximum indefinitely.

Example: AGENT_SESSION_MAX_SECONDS=86400

Source: pasted installation configuration; config\deployment.env.example

### AGENT_STUCK_RUN_SECONDS

Telemetry threshold for stale or stuck runs in seconds, example 900. This is not the workflow execution deadline.

Example: AGENT_STUCK_RUN_SECONDS=900

Source: pasted installation configuration; config\deployment.env.example

### COMPANION_LLM_ENABLED

Use true or false. Default false. Enables optional Ollama summaries of retrieved evidence. Evidence retrieval, service authorization and session handling remain separate. Unavailable generation must not be interpreted as missing source data.

Example: COMPANION_LLM_ENABLED=false

Source: .env.local; pasted installation configuration; config\deployment.env.example

### COMPANION_RETRIEVAL_TIMEOUT_SECONDS

Timeout for companion evidence retrieval in seconds. Example 15. Retrieval and optional text generation have separate failure paths.

Example: COMPANION_RETRIEVAL_TIMEOUT_SECONDS=15

Source: pasted installation configuration; config\deployment.env.example

### ONTOLOGY_AGENT_ALLOWED_ROOTS

Semicolon-separated permitted local input roots. Example data;ontology;backend/test_data;ontology_uploads. Restricts ontology-agent filesystem access.

Example: ONTOLOGY_AGENT_ALLOWED_ROOTS=data;ontology;backend/test_data;ontology_uploads

Source: pasted installation configuration; config\deployment.env.example

### ONTOLOGY_AGENT_LLM_ENABLED

Use true or false. Default false. Enables optional model-generated review questions in ontology orchestration; it does not replace deterministic inspection, grant approval, or publish mappings. Provider reachability is still required.

Example: ONTOLOGY_AGENT_LLM_ENABLED=false

Source: .env.local; pasted installation configuration; config\deployment.env.example

### ONTOLOGY_AGENT_MAX_BYTES

Ontology-agent input limit in bytes, example 26214400 or 25 MiB. Separate from generic agent and ontology registration limits.

Example: ONTOLOGY_AGENT_MAX_BYTES=26214400

Source: pasted installation configuration; config\deployment.env.example

### ONTOLOGY_MAX_UPLOAD_BYTES

Maximum RDF/OWL registration upload size in bytes, example 26214400 or 25 MiB.

Example: ONTOLOGY_MAX_UPLOAD_BYTES=26214400

Source: pasted installation configuration; config\deployment.env.example

## Database storage and deployment identity

### ARTIFACT_STORAGE

Absolute durable artifact directory shared by services and workers on the VM. The service identity needs appropriate filesystem permissions. Avoid temporary storage.

Example: ARTIFACT_STORAGE=C:\DEPO\data\artifacts

Source: pasted installation configuration; config\deployment.env.example

### DEPO_CEIM_IDENTITY_MODE

scoped uses tenant/project/source-system identities for new CEIM publications. legacy is an explicit compatibility option; do not mix unrelated source systems.

Example: DEPO_CEIM_IDENTITY_MODE=scoped

Source: pasted installation configuration; config\deployment.env.example

### DEPO_DATABASE_SCHEMA

PostgreSQL schema containing DEPO tables. Deployment example: semantic. Run schema validation and migrations against the selected database and schema.

Example: DEPO_DATABASE_SCHEMA=semantic

Source: pasted installation configuration; config\deployment.env.example

### DEPO_DATABASE_URL

PostgreSQL connection URL for the control plane, credentials and durable workflow state. Configure a customer-managed least-privilege role. Include the required TLS mode. The URL contains credentials and must remain server-side.

Example: DEPO_DATABASE_URL=postgresql://depo_app:<password>@<postgres-host>:5432/<database>?sslmode=require

Source: pasted installation configuration; config\deployment.env.example

### DEPO_MAX_INGEST_BYTES

Maximum ingestion payload size in bytes. Example 524288000 is 500 MiB. Align gateway upload limits and disk capacity with this limit.

Example: DEPO_MAX_INGEST_BYTES=524288000

Source: pasted installation configuration; config\deployment.env.example

### DEPO_POSTGRES_BIN_DIR

PostgreSQL executable directory for portable mode. Use an absolute path accessible to the launcher account.

Example: DEPO_POSTGRES_BIN_DIR=

Source: pasted installation configuration; config\deployment.env.example

### DEPO_POSTGRES_CONNECT_TIMEOUT_SECONDS

Bounds each PostgreSQL connection attempt in seconds. Accepted deployment range: 1–60; example 10. A higher startup wait does not fix invalid connection settings.

Example: DEPO_POSTGRES_CONNECT_TIMEOUT_SECONDS=10

Source: pasted installation configuration; config\deployment.env.example

### DEPO_POSTGRES_DATA_DIR

Initialized PostgreSQL cluster directory for portable mode. This is database storage, not the application artifact directory.

Example: DEPO_POSTGRES_DATA_DIR=

Source: pasted installation configuration; config\deployment.env.example

### DEPO_POSTGRES_MODE

Database management choice: external for customer-managed PostgreSQL, service for an explicitly named Windows service, or portable for explicitly configured initialized cluster paths.

Example: DEPO_POSTGRES_MODE=external

Source: pasted installation configuration; config\deployment.env.example

### DEPO_POSTGRES_SERVICE_NAME

Exact Windows PostgreSQL service name when service mode is selected. Do not rely on automatic selection of an unrelated local database service.

Example: DEPO_POSTGRES_SERVICE_NAME=

Source: pasted installation configuration; config\deployment.env.example

### DEPO_PROJECT_ID

Project identity within a customer scope. Keep it stable for retained semantic records and shared-store isolation.

Example: DEPO_PROJECT_ID=<project-id>

Source: pasted installation configuration; config\deployment.env.example

### DEPO_TENANT_ID

Customer identity used for scoped semantic identities and memory isolation. Assign a stable unique value when stores are shared.

Example: DEPO_TENANT_ID=<customer-id>

Source: pasted installation configuration; config\deployment.env.example

## Authentication and central credentials

### API_ACTOR

Actor identity associated with the optional trusted-internal token. Example ui-user. This does not create a browser login.

Example: API_ACTOR=ui-user

Source: pasted installation configuration; config\deployment.env.example

### API_TOKEN

Optional legacy trusted-internal token. Do not use it as a substitute for Entra gateway identity or the distinct registered credential profiles.

Example: API_TOKEN=<secret; never published>

Source: pasted installation configuration; config\deployment.env.example

### AUTH_MODE

API authentication mode. token enables registered API-key authentication; entra uses trusted gateway identity forwarding. disabled is restricted to loopback development. Keep routing and gateway configuration consistent.

Example: AUTH_MODE=token

Source: pasted installation configuration; config\deployment.env.example

### DEPO_ALLOW_INSECURE_LOCAL_AUTH

Explicit local development authentication exception. Deployment example false. Do not use it to bypass gateway security in a customer deployment.

Example: DEPO_ALLOW_INSECURE_LOCAL_AUTH=false

Source: pasted installation configuration; config\deployment.env.example

### DEPO_CREDENTIAL_STORE

Incoming key authority: postgres for central registered profiles, environment for legacy environment-backed validation. Reinstallation does not overwrite existing central keys.

Example: DEPO_CREDENTIAL_STORE=postgres

Source: pasted installation configuration; config\deployment.env.example

### DEPO_REQUIRE_TOKEN_ACTOR

true requires configured actor identities for token profiles. Use server-assigned identities; do not trust a browser-supplied actor.

Example: DEPO_REQUIRE_TOKEN_ACTOR=false

Source: pasted installation configuration; config\deployment.env.example

### DEPO_TOKEN_EXPIRES_AT

Optional default token expiry as a UTC ISO timestamp. A profile-specific expiry overrides this value. Blank means no explicit deadline from this setting.

Example: DEPO_TOKEN_EXPIRES_AT=

Source: pasted installation configuration; config\deployment.env.example

### DEPO_TRUSTED_GATEWAY_IPS

Comma-separated private addresses of gateways permitted to forward identity headers in Entra mode. Trust only the actual gateway peers.

Example: DEPO_TRUSTED_GATEWAY_IPS=<gateway-private-ip>

Source: pasted installation configuration; config\deployment.env.example

## Network and listener configuration

### ALLOWED_ORIGINS

Comma-separated exact HTTP/HTTPS browser origins. Paths, trailing slashes and wildcards are rejected at startup. Example http://localhost:3000. A malformed value can prevent schema-sets from starting.

Example: ALLOWED_ORIGINS=https://<customer-frontend-host>

Source: pasted installation configuration; config\deployment.env.example

### DEPO_APIM_SUBSCRIPTION_KEY

Optional server-side API Management subscription secret. Do not compile it into frontend variables. It is separate from the DEPO application credential profiles.

Example: DEPO_APIM_SUBSCRIPTION_KEY=<secret; never published>

Source: pasted installation configuration; config\deployment.env.example

### DEPO_API_GATEWAY_URL

Gateway HTTP/HTTPS root without a service suffix or /api/v1. Entra gateway routing requires HTTPS. Do not include credentials, query parameters or fragments.

Example: DEPO_API_GATEWAY_URL=

Source: pasted installation configuration; config\deployment.env.example

### DEPO_FRONTEND_HOST

Optional frontend bind address. Blank follows DEPO_SERVICE_HOST. Explicit launcher -BindHost overrides the file.

Example: DEPO_FRONTEND_HOST=

Source: pasted installation configuration; config\deployment.env.example

### DEPO_FRONTEND_PORT

Frontend integer port, normally 3000. Explicit launcher -Port overrides the file. Text such as 3000rr fails integer parsing. Update allowed origins when changing the port.

Example: DEPO_FRONTEND_PORT=3000

Source: pasted installation configuration; config\deployment.env.example

### DEPO_LOCAL_SERVICE_HOST

Reachable hostname or IPv4 address for direct service routing, without a scheme or port. 127.0.0.1 works only when the browser runs on the service VM.

Example: DEPO_LOCAL_SERVICE_HOST=127.0.0.1

Source: pasted installation configuration; config\deployment.env.example

### DEPO_ROUTING_MODE

local derives direct service URLs on ports 8010–8019 and requires token mode. gateway derives service URLs under DEPO_API_GATEWAY_URL. Blank preserves explicit URLs.

Example: DEPO_ROUTING_MODE=local

Source: pasted installation configuration; config\deployment.env.example

### DEPO_SERVICE_HOST

API listener bind address. A private interface or loopback is appropriate depending on gateway topology. A bind address such as 0.0.0.0 is not a browser destination.

Example: DEPO_SERVICE_HOST=127.0.0.1

Source: pasted installation configuration; config\deployment.env.example

## Registered application credentials

### ADMIN_API_KEY

Admin bootstrap and connection of registered service credentials. Use a distinct long random secret. Central registration stores a digest, not a plaintext key. Applying profiles does not sign the browser in. Rotate deliberately and reconnect browser sessions after rotation.

Example: ADMIN_API_KEY=<secret; never published>

Source: pasted installation configuration

### AGENTIC_APPROVAL_TOKEN

Protected agentic workflow actions. Use a distinct long random secret. Central registration stores a digest, not a plaintext key. Applying profiles does not sign the browser in. Rotate deliberately and reconnect browser sessions after rotation.

Example: AGENTIC_APPROVAL_TOKEN=<secret; never published>

Source: pasted installation configuration; config\deployment.env.example

### ARTIFACT_RETENTION_APPROVAL_TOKEN

Artifact retention approval. Use a distinct long random secret. Central registration stores a digest, not a plaintext key. Applying profiles does not sign the browser in. Rotate deliberately and reconnect browser sessions after rotation.

Example: ARTIFACT_RETENTION_APPROVAL_TOKEN=<secret; never published>

Source: pasted installation configuration; config\deployment.env.example

### CATALOG_SERVICE_TOKEN

Catalog service authorization. Use a distinct long random secret. Central registration stores a digest, not a plaintext key. Applying profiles does not sign the browser in. Rotate deliberately and reconnect browser sessions after rotation.

Example: CATALOG_SERVICE_TOKEN=<secret; never published>

Source: pasted installation configuration; config\deployment.env.example

### CEIM_PUBLISH_APPROVAL_TOKEN

CEIM publication approval. Use a distinct long random secret. Central registration stores a digest, not a plaintext key. Applying profiles does not sign the browser in. Rotate deliberately and reconnect browser sessions after rotation.

Example: CEIM_PUBLISH_APPROVAL_TOKEN=<secret; never published>

Source: pasted installation configuration; config\deployment.env.example

### CEIM_RESOLUTION_APPROVAL_TOKEN

CEIM resolution approval. Use a distinct long random secret. Central registration stores a digest, not a plaintext key. Applying profiles does not sign the browser in. Rotate deliberately and reconnect browser sessions after rotation.

Example: CEIM_RESOLUTION_APPROVAL_TOKEN=<secret; never published>

Source: pasted installation configuration; config\deployment.env.example

### DATA_JOB_APPROVAL_TOKEN

Data-job approval. Use a distinct long random secret. Central registration stores a digest, not a plaintext key. Applying profiles does not sign the browser in. Rotate deliberately and reconnect browser sessions after rotation.

Example: DATA_JOB_APPROVAL_TOKEN=<secret; never published>

Source: pasted installation configuration; config\deployment.env.example

### DATA_JOB_EXECUTION_TOKEN

Approved data-job execution. Use a distinct long random secret. Central registration stores a digest, not a plaintext key. Applying profiles does not sign the browser in. Rotate deliberately and reconnect browser sessions after rotation.

Example: DATA_JOB_EXECUTION_TOKEN=<secret; never published>

Source: pasted installation configuration; config\deployment.env.example

### DATA_PRODUCT_APPROVAL_TOKEN

Data-product approval and publication. Use a distinct long random secret. Central registration stores a digest, not a plaintext key. Applying profiles does not sign the browser in. Rotate deliberately and reconnect browser sessions after rotation.

Example: DATA_PRODUCT_APPROVAL_TOKEN=<secret; never published>

Source: pasted installation configuration; config\deployment.env.example

### GRAPH_PUBLICATION_TOKEN

Canonical graph publication. Use a distinct long random secret. Central registration stores a digest, not a plaintext key. Applying profiles does not sign the browser in. Rotate deliberately and reconnect browser sessions after rotation.

Example: GRAPH_PUBLICATION_TOKEN=<secret; never published>

Source: pasted installation configuration; config\deployment.env.example

### GRAPH_READ_TOKEN

Protected graph reads. Use a distinct long random secret. Central registration stores a digest, not a plaintext key. Applying profiles does not sign the browser in. Rotate deliberately and reconnect browser sessions after rotation.

Example: GRAPH_READ_TOKEN=<secret; never published>

Source: pasted installation configuration; config\deployment.env.example

### INGESTION_WRITE_TOKEN

Source ingestion writes. Use a distinct long random secret. Central registration stores a digest, not a plaintext key. Applying profiles does not sign the browser in. Rotate deliberately and reconnect browser sessions after rotation.

Example: INGESTION_WRITE_TOKEN=<secret; never published>

Source: pasted installation configuration; config\deployment.env.example

### ONTOLOGY_APPROVAL_TOKEN

Ontology approval. Use a distinct long random secret. Central registration stores a digest, not a plaintext key. Applying profiles does not sign the browser in. Rotate deliberately and reconnect browser sessions after rotation.

Example: ONTOLOGY_APPROVAL_TOKEN=<secret; never published>

Source: pasted installation configuration; config\deployment.env.example

### SPARQL_FEDERATION_APPROVAL_TOKEN

SPARQL federation approval. Use a distinct long random secret. Central registration stores a digest, not a plaintext key. Applying profiles does not sign the browser in. Rotate deliberately and reconnect browser sessions after rotation.

Example: SPARQL_FEDERATION_APPROVAL_TOKEN=<secret; never published>

Source: pasted installation configuration; config\deployment.env.example

### SPEED_EVENT_TOKEN

Speed-event authorization. Use a distinct long random secret. Central registration stores a digest, not a plaintext key. Applying profiles does not sign the browser in. Rotate deliberately and reconnect browser sessions after rotation.

Example: SPEED_EVENT_TOKEN=<secret; never published>

Source: pasted installation configuration; config\deployment.env.example

### SPEED_PATH_APPROVAL_TOKEN

Speed-path approval. Use a distinct long random secret. Central registration stores a digest, not a plaintext key. Applying profiles does not sign the browser in. Rotate deliberately and reconnect browser sessions after rotation.

Example: SPEED_PATH_APPROVAL_TOKEN=<secret; never published>

Source: pasted installation configuration; config\deployment.env.example

### VOCABULARY_APPROVAL_TOKEN

Vocabulary approval. Use a distinct long random secret. Central registration stores a digest, not a plaintext key. Applying profiles does not sign the browser in. Rotate deliberately and reconnect browser sessions after rotation.

Example: VOCABULARY_APPROVAL_TOKEN=<secret; never published>

Source: pasted installation configuration; config\deployment.env.example

## OSLC and digital twin integrations

### DT_AGENT_ENABLED

Enables digital-twin gateway integration. Requires a configured HTTPS gateway and gateway token.

Example: DT_AGENT_ENABLED=false

Source: pasted installation configuration; config\deployment.env.example

### DT_AGENT_GATEWAY_TOKEN

Server-side digital-twin gateway authentication secret. It is separate from the registered DEPO approval profiles.

Example: DT_AGENT_GATEWAY_TOKEN=<secret; never published>

Source: pasted installation configuration; config\deployment.env.example

### DT_AGENT_GATEWAY_URL

HTTPS base address of the provisioned digital-twin gateway.

Example: DT_AGENT_GATEWAY_URL=

Source: pasted installation configuration; config\deployment.env.example

### OSLC_BASE_URL

Public API base used to construct OSLC resources; resource paths append /oslc. Use the externally reachable address rather than an internal bind address.

Example: OSLC_BASE_URL=https://<customer-api-host>

Source: pasted installation configuration; config\deployment.env.example

### OSLC_CLIENT_TIMEOUT_SECONDS

Remote OSLC request timeout in seconds. Deployment example 20.

Example: OSLC_CLIENT_TIMEOUT_SECONDS=20

Source: pasted installation configuration; config\deployment.env.example

### OSLC_REMOTE_BASE_URL

HTTP/HTTPS base of the external OSLC provider. Independent from the local OSLC public base.

Example: OSLC_REMOTE_BASE_URL=

Source: pasted installation configuration; config\deployment.env.example

### OSLC_REMOTE_ENABLED

Enables access to a configured remote OSLC provider. Requires its remote URL and applicable authentication.

Example: OSLC_REMOTE_ENABLED=false

Source: pasted installation configuration; config\deployment.env.example

### OSLC_REMOTE_TOKEN

Optional remote-provider authentication secret retained server-side.

Example: OSLC_REMOTE_TOKEN=<secret; never published>

Source: pasted installation configuration; config\deployment.env.example

### OSLC_TRS_STORE

TRS change-event storage selector. postgres is the deployment default; file storage is for isolated development and tests.

Example: OSLC_TRS_STORE=postgres

Source: pasted installation configuration; config\deployment.env.example

## Pipeline and Spark execution

### DEPO_HADOOP_HOME

Native Windows Hadoop helper directory required by Windows Spark. Leave unset on Linux; use an approved helper runtime.

Example: DEPO_HADOOP_HOME=<windows-only-absolute-path-to-approved-hadoop-helpers>

Source: config\spark.env.example

### DEPO_JAVA_HOME

Absolute JDK directory for Spark. The supplied example uses JDK 21. Ensure the service account can execute this runtime.

Example: DEPO_JAVA_HOME=<absolute-path-to-jdk-21>

Source: config\spark.env.example

### DEPO_PIPELINE_EXECUTION_MODE

worker executes durable approved jobs outside the HTTP API through PostgreSQL leases. inline remains a developer compatibility option.

Example: DEPO_PIPELINE_EXECUTION_MODE=worker

Source: pasted installation configuration; config\deployment.env.example; config\spark.env.example

### DEPO_PIPELINE_LEASE_SECONDS

Duration of a worker job lease in seconds. Example 300. Coordinate with worker renewal and recovery so concurrent workers do not execute the same leased work.

Example: DEPO_PIPELINE_LEASE_SECONDS=300

Source: pasted installation configuration; config\deployment.env.example; config\spark.env.example

### DEPO_PIPELINE_POLL_SECONDS

Worker queue polling interval in seconds. Example 5. Shorter polling increases database activity.

Example: DEPO_PIPELINE_POLL_SECONDS=5

Source: pasted installation configuration; config\deployment.env.example; config\spark.env.example

### DEPO_PIPELINE_SCHEDULER_ENABLED

Boolean switch for pipeline scheduling. Example false. A durable worker can still execute approved jobs when scheduling is disabled.

Example: DEPO_PIPELINE_SCHEDULER_ENABLED=false

Source: pasted installation configuration; config\deployment.env.example; config\spark.env.example

### DEPO_PIPELINE_WORKER_STALE_SECONDS

Worker heartbeat staleness threshold in seconds. Example 60. Used to identify workers that are no longer reporting activity.

Example: DEPO_PIPELINE_WORKER_STALE_SECONDS=60

Source: pasted installation configuration; config\deployment.env.example; config\spark.env.example

### DEPO_SPARK_ENABLED

Enables optional Spark execution. false does not disable the durable worker or its non-Spark jobs.

Example: DEPO_SPARK_ENABLED=false

Source: pasted installation configuration; config\deployment.env.example; config\spark.env.example

### DEPO_SPARK_HOME

Absolute directory of the provisioned Spark distribution. The example names Spark 4.1.2. This example file is not loaded automatically; merge selected settings into the deployment file.

Example: DEPO_SPARK_HOME=<absolute-path-to-spark-4.1.2-bin-hadoop3>

Source: config\spark.env.example

### DEPO_SPARK_MASTER

Spark execution master. local[2] uses two local execution threads. Choose a provisioned remote master only when that topology is configured.

Example: DEPO_SPARK_MASTER=local[2]

Source: config\spark.env.example

### DEPO_SPARK_NEO4J_ENABLED

Enables optional Spark Neo4j read integration. Requires the matching connector package and compatible Spark/Scala runtime.

Example: DEPO_SPARK_NEO4J_ENABLED=false

Source: pasted installation configuration; config\deployment.env.example; config\spark.env.example

### DEPO_SPARK_NEO4J_PACKAGE

Neo4j Spark connector coordinate. The supplied example targets connector 6.0 with Spark 4.0–4.1 and Scala 2.13. Match the installed runtime.

Example: DEPO_SPARK_NEO4J_PACKAGE=org.neo4j.connectors:spark:6.0.0-s_2.13

Source: config\spark.env.example

### DEPO_SPARK_OUTPUT_ROOT

Durable Spark output directory accessible to the pipeline process and downstream readers.

Example: DEPO_SPARK_OUTPUT_ROOT=<absolute-path-to-spark-output>

Source: config\spark.env.example

### DEPO_SPARK_POSTGRES_DRIVER_JAR

Absolute path to the PostgreSQL JDBC driver JAR. Verify that the Spark process can read it; this setting does not download the driver.

Example: DEPO_SPARK_POSTGRES_DRIVER_JAR=C:\DEPO\drivers\postgresql-42.7.13.jar

Source: pasted installation configuration; config\deployment.env.example; config\spark.env.example

### DEPO_SPARK_POSTGRES_ENABLED

Enables optional read-side Spark JDBC access to the configured PostgreSQL database. Provision the JDBC driver separately.

Example: DEPO_SPARK_POSTGRES_ENABLED=false

Source: pasted installation configuration; config\deployment.env.example; config\spark.env.example

## Individual service routing

### AGENTIC_SERVICE_URL

Server-to-server agentic API base including /api/v1. Routing mode can derive this setting; explicit URLs apply when unified routing is blank.

Example: AGENTIC_SERVICE_URL=http://127.0.0.1:8012/api/v1

Source: pasted installation configuration; config\deployment.env.example

### CEIM_SERVICE_URL

Server-to-server ceim API base including /api/v1. Routing mode can derive this setting; explicit URLs apply when unified routing is blank.

Example: CEIM_SERVICE_URL=http://127.0.0.1:8018/api/v1

Source: infra/windows/runtime-config.ps1

### DATA_CATALOG_URL

Server-to-server catalog API base including /api/v1. Routing mode can derive this setting; explicit URLs apply when unified routing is blank.

Example: DATA_CATALOG_URL=http://127.0.0.1:8016/api/v1

Source: infra/windows/runtime-config.ps1

### DATA_PIPELINE_SERVICE_URL

Server-to-server data pipeline API base including /api/v1. Routing mode can derive this setting; explicit URLs apply when unified routing is blank.

Example: DATA_PIPELINE_SERVICE_URL=http://127.0.0.1:8019/api/v1

Source: infra/windows/runtime-config.ps1

### DATA_PRODUCT_SERVICE_URL

Server-to-server data product API base including /api/v1. Routing mode can derive this setting; explicit URLs apply when unified routing is blank.

Example: DATA_PRODUCT_SERVICE_URL=http://127.0.0.1:8017/api/v1

Source: infra/windows/runtime-config.ps1

### DEPO_GATEWAY_AGENTIC_PATH

Optional relative gateway suffix for agentic. Use path segments without leading slash or /api/v1. Default suffix: agentic.

Example: DEPO_GATEWAY_AGENTIC_PATH=agentic

Source: infra/windows/runtime-config.ps1

### DEPO_GATEWAY_CATALOG_PATH

Optional relative gateway suffix for catalog. Use path segments without leading slash or /api/v1. Default suffix: catalog.

Example: DEPO_GATEWAY_CATALOG_PATH=catalog

Source: infra/windows/runtime-config.ps1

### DEPO_GATEWAY_CEIM_PATH

Optional relative gateway suffix for ceim. Use path segments without leading slash or /api/v1. Default suffix: ceim.

Example: DEPO_GATEWAY_CEIM_PATH=ceim

Source: infra/windows/runtime-config.ps1

### DEPO_GATEWAY_DATA_PIPELINE_PATH

Optional relative gateway suffix for data pipeline. Use path segments without leading slash or /api/v1. Default suffix: data-pipeline.

Example: DEPO_GATEWAY_DATA_PIPELINE_PATH=data-pipeline

Source: infra/windows/runtime-config.ps1

### DEPO_GATEWAY_DATA_PRODUCT_PATH

Optional relative gateway suffix for data product. Use path segments without leading slash or /api/v1. Default suffix: data-products.

Example: DEPO_GATEWAY_DATA_PRODUCT_PATH=data-products

Source: infra/windows/runtime-config.ps1

### DEPO_GATEWAY_GRAPH_PATH

Optional relative gateway suffix for graph. Use path segments without leading slash or /api/v1. Default suffix: graph.

Example: DEPO_GATEWAY_GRAPH_PATH=graph

Source: infra/windows/runtime-config.ps1

### DEPO_GATEWAY_INGESTION_PATH

Optional relative gateway suffix for ingestion. Use path segments without leading slash or /api/v1. Default suffix: ingestion.

Example: DEPO_GATEWAY_INGESTION_PATH=ingestion

Source: infra/windows/runtime-config.ps1

### DEPO_GATEWAY_ONTOLOGY_PATH

Optional relative gateway suffix for ontology. Use path segments without leading slash or /api/v1. Default suffix: ontology.

Example: DEPO_GATEWAY_ONTOLOGY_PATH=ontology

Source: infra/windows/runtime-config.ps1

### DEPO_GATEWAY_OSLC_PATH

Optional relative gateway suffix for oslc. Use path segments without leading slash or /api/v1. Default suffix: oslc.

Example: DEPO_GATEWAY_OSLC_PATH=oslc

Source: infra/windows/runtime-config.ps1

### DEPO_GATEWAY_QIF_PATH

Optional relative gateway suffix for qif. Use path segments without leading slash or /api/v1. Default suffix: qif.

Example: DEPO_GATEWAY_QIF_PATH=qif

Source: infra/windows/runtime-config.ps1

### GRAPH_SERVICE_URL

Server-to-server graph API base including /api/v1. Routing mode can derive this setting; explicit URLs apply when unified routing is blank.

Example: GRAPH_SERVICE_URL=http://127.0.0.1:8013/api/v1

Source: pasted installation configuration; config\deployment.env.example

### INGESTION_SERVICE_URL

Server-to-server ingestion API base including /api/v1. Routing mode can derive this setting; explicit URLs apply when unified routing is blank.

Example: INGESTION_SERVICE_URL=http://127.0.0.1:8014/api/v1

Source: infra/windows/runtime-config.ps1

### ONTOLOGY_SERVICE_URL

Server-to-server ontology API base including /api/v1. Routing mode can derive this setting; explicit URLs apply when unified routing is blank.

Example: ONTOLOGY_SERVICE_URL=http://127.0.0.1:8011/api/v1

Source: infra/windows/runtime-config.ps1

### OSLC_SERVICE_URL

Server-to-server oslc API base including /api/v1. Routing mode can derive this setting; explicit URLs apply when unified routing is blank.

Example: OSLC_SERVICE_URL=http://127.0.0.1:8015/api/v1

Source: infra/windows/runtime-config.ps1

### QIF_SERVICE_URL

Server-to-server qif API base including /api/v1. Routing mode can derive this setting; explicit URLs apply when unified routing is blank.

Example: QIF_SERVICE_URL=http://127.0.0.1:8010/api/v1

Source: infra/windows/runtime-config.ps1

## Document OCR

### DOCUMENT_EASYOCR_ALLOW_DOWNLOAD

Boolean permission for EasyOCR model downloads. false supports controlled offline provisioning.

Example: DOCUMENT_EASYOCR_ALLOW_DOWNLOAD=false

Source: pasted installation configuration; config\deployment.env.example

### DOCUMENT_EASYOCR_MODEL_DIR

Directory holding EasyOCR model files. Provision models before running offline workloads.

Example: DOCUMENT_EASYOCR_MODEL_DIR=C:\DEPO\models\easyocr

Source: pasted installation configuration; config\deployment.env.example

### DOCUMENT_MAX_OCR_PAGES

Maximum pages processed by OCR, example 100. Bounds resource usage for large documents.

Example: DOCUMENT_MAX_OCR_PAGES=100

Source: pasted installation configuration; config\deployment.env.example

### DOCUMENT_OCR_GPU

Boolean request for GPU OCR execution. Requires a compatible installed provider and GPU runtime.

Example: DOCUMENT_OCR_GPU=false

Source: pasted installation configuration; config\deployment.env.example

### DOCUMENT_OCR_LANGUAGES

Language selection for OCR, example en. Install the language resources required by the selected OCR provider.

Example: DOCUMENT_OCR_LANGUAGES=en

Source: pasted installation configuration; config\deployment.env.example

### DOCUMENT_OCR_PROVIDER

OCR provider selector. auto prefers available Tesseract and otherwise installed EasyOCR. OCR extracts evidence and does not authorize semantic publication.

Example: DOCUMENT_OCR_PROVIDER=auto

Source: pasted installation configuration; config\deployment.env.example

## Frontend configuration

### REACT_APP_AGENTIC_ENABLED

Optional legacy low-code ontology component adapter flag in the frontend example. Treat as adapter-specific; it does not enable backend authorization or agent workflows.

Example: REACT_APP_AGENTIC_ENABLED=false

Source: frontend\.env.example

### REACT_APP_AGENTIC_SERVICE_URL

Service URL for the optional legacy component adapter, not the standard VITE service routing setting.

Example: REACT_APP_AGENTIC_SERVICE_URL=

Source: frontend\.env.example

### REACT_APP_API_VERSION

Legacy frontend configuration API-version label, example v1. Check the actual adapter consumer before relying on it.

Example: REACT_APP_API_VERSION=v1

Source: frontend\.env.example

### REACT_APP_DEBUG

Legacy frontend debug flag. Keep false in customer deployments; check adapter use before relying on it.

Example: REACT_APP_DEBUG=false

Source: frontend\.env.example

### REACT_APP_ENV

Legacy frontend environment label, example development. Does not configure server deployment mode.

Example: REACT_APP_ENV=development

Source: frontend\.env.example

### REACT_APP_LOG_LEVEL

Legacy frontend logging preference, example info. This is not the backend log-level setting.

Example: REACT_APP_LOG_LEVEL=info

Source: frontend\.env.example

### REACT_APP_REQUEST_TIMEOUT

Legacy frontend request timeout example 60000 milliseconds. Do not confuse with backend timeout values measured in seconds.

Example: REACT_APP_REQUEST_TIMEOUT=60000

Source: frontend\.env.example

### REACT_APP_SIRIUS_WEB_URL

Optional Sirius Web integration address in the frontend example.

Example: REACT_APP_SIRIUS_WEB_URL=http://localhost:8080

Source: frontend\.env.example

### VITE_AGENTIC_SERVICE_URL

Browser-visible agentic service base without /api/v1. Use a host reachable from the browser. Unified routing derives the corresponding value.

Example: VITE_AGENTIC_SERVICE_URL=http://127.0.0.1:8012

Source: frontend\.env.example

### VITE_API_GATEWAY_URL

Browser-visible gateway root. Configure before building or through supported runtime routing. Never embed authentication secrets in VITE variables.

Example: VITE_API_GATEWAY_URL=

Source: frontend\.env.example

### VITE_BACKEND_URL

Legacy aggregate backend base. Leave blank for the independent-service topology.

Example: VITE_BACKEND_URL=# Legacy aggregate API only; leave empty for service topology.

Source: frontend\.env.example

### VITE_CATALOG_SERVICE_URL

Browser-visible catalog service base without /api/v1. Use a host reachable from the browser. Unified routing derives the corresponding value.

Example: VITE_CATALOG_SERVICE_URL=http://127.0.0.1:8016

Source: frontend\.env.example

### VITE_CEIM_SERVICE_URL

Browser-visible ceim service base without /api/v1. Use a host reachable from the browser. Unified routing derives the corresponding value.

Example: VITE_CEIM_SERVICE_URL=http://127.0.0.1:8018

Source: infra/windows/runtime-config.ps1

### VITE_DATA_PIPELINE_SERVICE_URL

Browser-visible data pipeline service base without /api/v1. Use a host reachable from the browser. Unified routing derives the corresponding value.

Example: VITE_DATA_PIPELINE_SERVICE_URL=http://127.0.0.1:8019

Source: frontend\.env.example

### VITE_DATA_PRODUCT_SERVICE_URL

Browser-visible data product service base without /api/v1. Use a host reachable from the browser. Unified routing derives the corresponding value.

Example: VITE_DATA_PRODUCT_SERVICE_URL=http://127.0.0.1:8017

Source: frontend\.env.example

### VITE_GRAPH_SERVICE_URL

Browser-visible graph service base without /api/v1. Use a host reachable from the browser. Unified routing derives the corresponding value.

Example: VITE_GRAPH_SERVICE_URL=http://127.0.0.1:8013

Source: frontend\.env.example

### VITE_INGESTION_SERVICE_URL

Browser-visible ingestion service base without /api/v1. Use a host reachable from the browser. Unified routing derives the corresponding value.

Example: VITE_INGESTION_SERVICE_URL=http://127.0.0.1:8014

Source: frontend\.env.example

### VITE_ONTOLOGY_SERVICE_URL

Browser-visible ontology service base without /api/v1. Use a host reachable from the browser. Unified routing derives the corresponding value.

Example: VITE_ONTOLOGY_SERVICE_URL=http://127.0.0.1:8011

Source: frontend\.env.example

### VITE_OSLC_SERVICE_URL

Browser-visible oslc service base without /api/v1. Use a host reachable from the browser. Unified routing derives the corresponding value.

Example: VITE_OSLC_SERVICE_URL=http://127.0.0.1:8015

Source: frontend\.env.example

### VITE_QIF_SERVICE_URL

Browser-visible qif service base without /api/v1. Use a host reachable from the browser. Unified routing derives the corresponding value.

Example: VITE_QIF_SERVICE_URL=http://127.0.0.1:8010

Source: frontend\.env.example

## Standalone ontology connectors

### DEPO_IIF_ADAPTER_SECURITY_ENABLED

Standalone compatibility adapter security flag. Review before enabling external access; the example defaults false.

Example: DEPO_IIF_ADAPTER_SECURITY_ENABLED=false

Source: standalone\ontology_agentic_service\.env.example

### DEPO_IIF_ADAPTER_TOKEN

Server-side access token for the standalone compatibility adapter when its security is enabled.

Example: DEPO_IIF_ADAPTER_TOKEN=<secret; never published>

Source: standalone\ontology_agentic_service\.env.example

### DEPO_IIF_MAX_UPLOAD_BYTES

Standalone compatibility adapter upload limit in bytes, example 52428800 or 50 MiB.

Example: DEPO_IIF_MAX_UPLOAD_BYTES=52428800

Source: standalone\ontology_agentic_service\.env.example

### DEPO_IIF_RUNTIME_ROOT

Standalone compatibility adapter runtime directory.

Example: DEPO_IIF_RUNTIME_ROOT=

Source: standalone\ontology_agentic_service\.env.example

### DEPO_IIF_UPLOAD_DIR

Upload directory for the standalone compatibility adapter; ensure the process identity has suitable permissions.

Example: DEPO_IIF_UPLOAD_DIR=

Source: standalone\ontology_agentic_service\.env.example

### DEPO_IIF_WORKFLOW_DIR

Workflow directory for the standalone existing-frontend compatibility adapter.

Example: DEPO_IIF_WORKFLOW_DIR=

Source: standalone\ontology_agentic_service\.env.example

### NEO4J_MCP_ALLOWED_TOOLS

Configured allow-list of connector tools when connector filtering is enabled.

Example: NEO4J_MCP_ALLOWED_TOOLS=

Source: standalone\ontology_agentic_service\.env.example

### NEO4J_MCP_ALLOW_WRITES

Explicit standalone MCP write permission flag. Example false. Connector access does not imply governed publication approval.

Example: NEO4J_MCP_ALLOW_WRITES=false

Source: standalone\ontology_agentic_service\.env.example

### NEO4J_MCP_ARGS_JSON

JSON array of command arguments, example []. Keep valid JSON on one environment-file line.

Example: NEO4J_MCP_ARGS_JSON=[]

Source: standalone\ontology_agentic_service\.env.example

### NEO4J_MCP_COMMAND

Executable for command-based MCP transport. Provision and validate the executable before enabling it.

Example: NEO4J_MCP_COMMAND=

Source: standalone\ontology_agentic_service\.env.example

### NEO4J_MCP_ENABLED

Standalone flag enabling the optional Neo4j MCP connector. Requires an HTTP endpoint or configured command transport.

Example: NEO4J_MCP_ENABLED=false

Source: standalone\ontology_agentic_service\.env.example

### NEO4J_MCP_ENV_JSON

JSON object of connector process environment overrides, example {}. It can contain secrets and must remain server-side.

Example: NEO4J_MCP_ENV_JSON=<secret; never published>

Source: standalone\ontology_agentic_service\.env.example

### NEO4J_MCP_SECURITY_ENABLED

Enables standalone connector-side tool filtering. The example defaults false; review this before exposing connector access.

Example: NEO4J_MCP_SECURITY_ENABLED=false

Source: standalone\ontology_agentic_service\.env.example

### NEO4J_MCP_URL

MCP connector URL when using HTTP transport. Leave blank for command transport.

Example: NEO4J_MCP_URL=

Source: standalone\ontology_agentic_service\.env.example

### ONTOLOGY_EXTERNAL_API_BASE_URL

Base address of the external ontology/context HTTP service for standalone tools.

Example: ONTOLOGY_EXTERNAL_API_BASE_URL=http://127.0.0.1:8000

Source: standalone\ontology_agentic_service\.env.example

### ONTOLOGY_EXTERNAL_API_ENABLED

Standalone ontology service flag enabling external_* HTTP tools. This file belongs to the separate standalone component.

Example: ONTOLOGY_EXTERNAL_API_ENABLED=false

Source: standalone\ontology_agentic_service\.env.example

### ONTOLOGY_EXTERNAL_API_TIMEOUT_SECONDS

Standalone external ontology HTTP timeout in seconds, example 30.

Example: ONTOLOGY_EXTERNAL_API_TIMEOUT_SECONDS=30

Source: standalone\ontology_agentic_service\.env.example

### ONTOLOGY_EXTERNAL_API_TOKEN

Optional server-side authentication token for the external ontology/context service.

Example: ONTOLOGY_EXTERNAL_API_TOKEN=<secret; never published>

Source: standalone\ontology_agentic_service\.env.example

### ONTOLOGY_EXTERNAL_CONTEXT_SEARCH_PATH

External context-search route, example /graphfilter.

Example: ONTOLOGY_EXTERNAL_CONTEXT_SEARCH_PATH=/graphfilter

Source: standalone\ontology_agentic_service\.env.example

### ONTOLOGY_EXTERNAL_REGISTERED_PATH

External registered-ontology route, example /api/v1/ontology/registered, resolved against the external base.

Example: ONTOLOGY_EXTERNAL_REGISTERED_PATH=/api/v1/ontology/registered

Source: standalone\ontology_agentic_service\.env.example

## Credential identity and expiry overrides

### ADMIN_API_KEY_ACTOR

Server-assigned actor for ADMIN_API_KEY. Use a stable accountable identity; required when actor enforcement applies.

Example: ADMIN_API_KEY_ACTOR=service-operator

Source: backend/depo_platform/credentials.py and security configuration

### ADMIN_API_KEY_EXPIRES_AT

Optional UTC ISO expiry for ADMIN_API_KEY. Overrides DEPO_TOKEN_EXPIRES_AT. Blank leaves the global fallback in effect.

Example: ADMIN_API_KEY_EXPIRES_AT=2027-01-01T00:00:00Z

Source: backend/depo_platform/credentials.py and security configuration

### AGENTIC_APPROVAL_TOKEN_ACTOR

Server-assigned actor for AGENTIC_APPROVAL_TOKEN. Use a stable accountable identity; required when actor enforcement applies.

Example: AGENTIC_APPROVAL_TOKEN_ACTOR=service-operator

Source: backend/depo_platform/credentials.py and security configuration

### AGENTIC_APPROVAL_TOKEN_EXPIRES_AT

Optional UTC ISO expiry for AGENTIC_APPROVAL_TOKEN. Overrides DEPO_TOKEN_EXPIRES_AT. Blank leaves the global fallback in effect.

Example: AGENTIC_APPROVAL_TOKEN_EXPIRES_AT=2027-01-01T00:00:00Z

Source: backend/depo_platform/credentials.py and security configuration

### ARTIFACT_RETENTION_APPROVAL_TOKEN_ACTOR

Server-assigned actor for ARTIFACT_RETENTION_APPROVAL_TOKEN. Use a stable accountable identity; required when actor enforcement applies.

Example: ARTIFACT_RETENTION_APPROVAL_TOKEN_ACTOR=service-operator

Source: backend/depo_platform/credentials.py and security configuration

### ARTIFACT_RETENTION_APPROVAL_TOKEN_EXPIRES_AT

Optional UTC ISO expiry for ARTIFACT_RETENTION_APPROVAL_TOKEN. Overrides DEPO_TOKEN_EXPIRES_AT. Blank leaves the global fallback in effect.

Example: ARTIFACT_RETENTION_APPROVAL_TOKEN_EXPIRES_AT=2027-01-01T00:00:00Z

Source: backend/depo_platform/credentials.py and security configuration

### CATALOG_SERVICE_TOKEN_ACTOR

Server-assigned actor for CATALOG_SERVICE_TOKEN. Use a stable accountable identity; required when actor enforcement applies.

Example: CATALOG_SERVICE_TOKEN_ACTOR=service-operator

Source: backend/depo_platform/credentials.py and security configuration

### CATALOG_SERVICE_TOKEN_EXPIRES_AT

Optional UTC ISO expiry for CATALOG_SERVICE_TOKEN. Overrides DEPO_TOKEN_EXPIRES_AT. Blank leaves the global fallback in effect.

Example: CATALOG_SERVICE_TOKEN_EXPIRES_AT=2027-01-01T00:00:00Z

Source: backend/depo_platform/credentials.py and security configuration

### CEIM_PUBLISH_APPROVAL_TOKEN_ACTOR

Server-assigned actor for CEIM_PUBLISH_APPROVAL_TOKEN. Use a stable accountable identity; required when actor enforcement applies.

Example: CEIM_PUBLISH_APPROVAL_TOKEN_ACTOR=service-operator

Source: backend/depo_platform/credentials.py and security configuration

### CEIM_PUBLISH_APPROVAL_TOKEN_EXPIRES_AT

Optional UTC ISO expiry for CEIM_PUBLISH_APPROVAL_TOKEN. Overrides DEPO_TOKEN_EXPIRES_AT. Blank leaves the global fallback in effect.

Example: CEIM_PUBLISH_APPROVAL_TOKEN_EXPIRES_AT=2027-01-01T00:00:00Z

Source: backend/depo_platform/credentials.py and security configuration

### CEIM_RESOLUTION_APPROVAL_TOKEN_ACTOR

Server-assigned actor for CEIM_RESOLUTION_APPROVAL_TOKEN. Use a stable accountable identity; required when actor enforcement applies.

Example: CEIM_RESOLUTION_APPROVAL_TOKEN_ACTOR=service-operator

Source: backend/depo_platform/credentials.py and security configuration

### CEIM_RESOLUTION_APPROVAL_TOKEN_EXPIRES_AT

Optional UTC ISO expiry for CEIM_RESOLUTION_APPROVAL_TOKEN. Overrides DEPO_TOKEN_EXPIRES_AT. Blank leaves the global fallback in effect.

Example: CEIM_RESOLUTION_APPROVAL_TOKEN_EXPIRES_AT=2027-01-01T00:00:00Z

Source: backend/depo_platform/credentials.py and security configuration

### DATA_JOB_APPROVAL_TOKEN_ACTOR

Server-assigned actor for DATA_JOB_APPROVAL_TOKEN. Use a stable accountable identity; required when actor enforcement applies.

Example: DATA_JOB_APPROVAL_TOKEN_ACTOR=service-operator

Source: backend/depo_platform/credentials.py and security configuration

### DATA_JOB_APPROVAL_TOKEN_EXPIRES_AT

Optional UTC ISO expiry for DATA_JOB_APPROVAL_TOKEN. Overrides DEPO_TOKEN_EXPIRES_AT. Blank leaves the global fallback in effect.

Example: DATA_JOB_APPROVAL_TOKEN_EXPIRES_AT=2027-01-01T00:00:00Z

Source: backend/depo_platform/credentials.py and security configuration

### DATA_JOB_EXECUTION_TOKEN_ACTOR

Server-assigned actor for DATA_JOB_EXECUTION_TOKEN. Use a stable accountable identity; required when actor enforcement applies.

Example: DATA_JOB_EXECUTION_TOKEN_ACTOR=service-operator

Source: backend/depo_platform/credentials.py and security configuration

### DATA_JOB_EXECUTION_TOKEN_EXPIRES_AT

Optional UTC ISO expiry for DATA_JOB_EXECUTION_TOKEN. Overrides DEPO_TOKEN_EXPIRES_AT. Blank leaves the global fallback in effect.

Example: DATA_JOB_EXECUTION_TOKEN_EXPIRES_AT=2027-01-01T00:00:00Z

Source: backend/depo_platform/credentials.py and security configuration

### DATA_PRODUCT_APPROVAL_TOKEN_ACTOR

Server-assigned actor for DATA_PRODUCT_APPROVAL_TOKEN. Use a stable accountable identity; required when actor enforcement applies.

Example: DATA_PRODUCT_APPROVAL_TOKEN_ACTOR=service-operator

Source: backend/depo_platform/credentials.py and security configuration

### DATA_PRODUCT_APPROVAL_TOKEN_EXPIRES_AT

Optional UTC ISO expiry for DATA_PRODUCT_APPROVAL_TOKEN. Overrides DEPO_TOKEN_EXPIRES_AT. Blank leaves the global fallback in effect.

Example: DATA_PRODUCT_APPROVAL_TOKEN_EXPIRES_AT=2027-01-01T00:00:00Z

Source: backend/depo_platform/credentials.py and security configuration

### GRAPH_PUBLICATION_TOKEN_ACTOR

Server-assigned actor for GRAPH_PUBLICATION_TOKEN. Use a stable accountable identity; required when actor enforcement applies.

Example: GRAPH_PUBLICATION_TOKEN_ACTOR=service-operator

Source: backend/depo_platform/credentials.py and security configuration

### GRAPH_PUBLICATION_TOKEN_EXPIRES_AT

Optional UTC ISO expiry for GRAPH_PUBLICATION_TOKEN. Overrides DEPO_TOKEN_EXPIRES_AT. Blank leaves the global fallback in effect.

Example: GRAPH_PUBLICATION_TOKEN_EXPIRES_AT=2027-01-01T00:00:00Z

Source: backend/depo_platform/credentials.py and security configuration

### GRAPH_READ_TOKEN_ACTOR

Server-assigned actor for GRAPH_READ_TOKEN. Use a stable accountable identity; required when actor enforcement applies.

Example: GRAPH_READ_TOKEN_ACTOR=service-operator

Source: backend/depo_platform/credentials.py and security configuration

### GRAPH_READ_TOKEN_EXPIRES_AT

Optional UTC ISO expiry for GRAPH_READ_TOKEN. Overrides DEPO_TOKEN_EXPIRES_AT. Blank leaves the global fallback in effect.

Example: GRAPH_READ_TOKEN_EXPIRES_AT=2027-01-01T00:00:00Z

Source: backend/depo_platform/credentials.py and security configuration

### INGESTION_WRITE_TOKEN_ACTOR

Server-assigned actor for INGESTION_WRITE_TOKEN. Use a stable accountable identity; required when actor enforcement applies.

Example: INGESTION_WRITE_TOKEN_ACTOR=service-operator

Source: backend/depo_platform/credentials.py and security configuration

### INGESTION_WRITE_TOKEN_EXPIRES_AT

Optional UTC ISO expiry for INGESTION_WRITE_TOKEN. Overrides DEPO_TOKEN_EXPIRES_AT. Blank leaves the global fallback in effect.

Example: INGESTION_WRITE_TOKEN_EXPIRES_AT=2027-01-01T00:00:00Z

Source: backend/depo_platform/credentials.py and security configuration

### ONTOLOGY_APPROVAL_TOKEN_ACTOR

Server-assigned actor for ONTOLOGY_APPROVAL_TOKEN. Use a stable accountable identity; required when actor enforcement applies.

Example: ONTOLOGY_APPROVAL_TOKEN_ACTOR=service-operator

Source: backend/depo_platform/credentials.py and security configuration

### ONTOLOGY_APPROVAL_TOKEN_EXPIRES_AT

Optional UTC ISO expiry for ONTOLOGY_APPROVAL_TOKEN. Overrides DEPO_TOKEN_EXPIRES_AT. Blank leaves the global fallback in effect.

Example: ONTOLOGY_APPROVAL_TOKEN_EXPIRES_AT=2027-01-01T00:00:00Z

Source: backend/depo_platform/credentials.py and security configuration

### SPARQL_FEDERATION_APPROVAL_TOKEN_ACTOR

Server-assigned actor for SPARQL_FEDERATION_APPROVAL_TOKEN. Use a stable accountable identity; required when actor enforcement applies.

Example: SPARQL_FEDERATION_APPROVAL_TOKEN_ACTOR=service-operator

Source: backend/depo_platform/credentials.py and security configuration

### SPARQL_FEDERATION_APPROVAL_TOKEN_EXPIRES_AT

Optional UTC ISO expiry for SPARQL_FEDERATION_APPROVAL_TOKEN. Overrides DEPO_TOKEN_EXPIRES_AT. Blank leaves the global fallback in effect.

Example: SPARQL_FEDERATION_APPROVAL_TOKEN_EXPIRES_AT=2027-01-01T00:00:00Z

Source: backend/depo_platform/credentials.py and security configuration

### SPEED_EVENT_TOKEN_ACTOR

Server-assigned actor for SPEED_EVENT_TOKEN. Use a stable accountable identity; required when actor enforcement applies.

Example: SPEED_EVENT_TOKEN_ACTOR=service-operator

Source: backend/depo_platform/credentials.py and security configuration

### SPEED_EVENT_TOKEN_EXPIRES_AT

Optional UTC ISO expiry for SPEED_EVENT_TOKEN. Overrides DEPO_TOKEN_EXPIRES_AT. Blank leaves the global fallback in effect.

Example: SPEED_EVENT_TOKEN_EXPIRES_AT=2027-01-01T00:00:00Z

Source: backend/depo_platform/credentials.py and security configuration

### SPEED_PATH_APPROVAL_TOKEN_ACTOR

Server-assigned actor for SPEED_PATH_APPROVAL_TOKEN. Use a stable accountable identity; required when actor enforcement applies.

Example: SPEED_PATH_APPROVAL_TOKEN_ACTOR=service-operator

Source: backend/depo_platform/credentials.py and security configuration

### SPEED_PATH_APPROVAL_TOKEN_EXPIRES_AT

Optional UTC ISO expiry for SPEED_PATH_APPROVAL_TOKEN. Overrides DEPO_TOKEN_EXPIRES_AT. Blank leaves the global fallback in effect.

Example: SPEED_PATH_APPROVAL_TOKEN_EXPIRES_AT=2027-01-01T00:00:00Z

Source: backend/depo_platform/credentials.py and security configuration

### VOCABULARY_APPROVAL_TOKEN_ACTOR

Server-assigned actor for VOCABULARY_APPROVAL_TOKEN. Use a stable accountable identity; required when actor enforcement applies.

Example: VOCABULARY_APPROVAL_TOKEN_ACTOR=service-operator

Source: backend/depo_platform/credentials.py and security configuration

### VOCABULARY_APPROVAL_TOKEN_EXPIRES_AT

Optional UTC ISO expiry for VOCABULARY_APPROVAL_TOKEN. Overrides DEPO_TOKEN_EXPIRES_AT. Blank leaves the global fallback in effect.

Example: VOCABULARY_APPROVAL_TOKEN_EXPIRES_AT=2027-01-01T00:00:00Z

Source: backend/depo_platform/credentials.py and security configuration

## Installation checks

- Validate PostgreSQL schema and connectivity before starting services. Keep application credentials separate from database, Neo4j, Ollama and APIM credentials.

- Register and validate application profiles in PostgreSQL, then connect registered credentials in Admin. Stored keys do not create a signed-in browser session; delegated sessions expire and rotation invalidates them.

- Use exact ALLOWED_ORIGINS and an integer frontend port. Invalid origin syntax caused the reported service startup failure; 3000rr caused frontend port parsing failure.

- Verify service addresses from the actual browser and from the application VM. A remote browser cannot use VM loopback addresses.

- Check Ollama /api/tags from the application VM and verify the exact generation and embedding models. Authentication and chat capability are separate checks.

- Inspect service error logs when a process exits before readiness. A longer startup timeout cannot fix a terminated process.

- A fresh installation can legitimately have zero catalog versions and retained packages. An approved publication creates product records; credential installation does not.

- Pause and cancel apply at tool boundaries. They do not undo writes or extend the original workflow execution deadline.

## Alphabetical variable index

ADMIN_API_KEY
ADMIN_API_KEY_ACTOR
ADMIN_API_KEY_EXPIRES_AT
AGENTIC_APPROVAL_TOKEN
AGENTIC_APPROVAL_TOKEN_ACTOR
AGENTIC_APPROVAL_TOKEN_EXPIRES_AT
AGENTIC_MAX_UPLOAD_BYTES
AGENTIC_RUN_TIMEOUT_SECONDS
AGENTIC_SERVICE_URL
AGENTIC_TOOL_TIMEOUT_SECONDS
AGENT_FAILURE_RATE_ALERT_THRESHOLD
AGENT_MEMORY_ENABLED
AGENT_MEMORY_NEO4J_DATABASE
AGENT_MEMORY_QUERY_TIMEOUT
AGENT_MEMORY_RETENTION_DAYS
AGENT_MEMORY_SCOPE
AGENT_PROMPT_VERSION
AGENT_SESSION_IDLE_SECONDS
AGENT_SESSION_MAX_SECONDS
AGENT_STUCK_RUN_SECONDS
ALLOWED_ORIGINS
API_ACTOR
API_TOKEN
ARTIFACT_RETENTION_APPROVAL_TOKEN
ARTIFACT_RETENTION_APPROVAL_TOKEN_ACTOR
ARTIFACT_RETENTION_APPROVAL_TOKEN_EXPIRES_AT
ARTIFACT_STORAGE
AURA_INSTANCEID
AURA_INSTANCENAME
AUTH_MODE
CATALOG_SERVICE_TOKEN
CATALOG_SERVICE_TOKEN_ACTOR
CATALOG_SERVICE_TOKEN_EXPIRES_AT
CEIM_PUBLISH_APPROVAL_TOKEN
CEIM_PUBLISH_APPROVAL_TOKEN_ACTOR
CEIM_PUBLISH_APPROVAL_TOKEN_EXPIRES_AT
CEIM_RESOLUTION_APPROVAL_TOKEN
CEIM_RESOLUTION_APPROVAL_TOKEN_ACTOR
CEIM_RESOLUTION_APPROVAL_TOKEN_EXPIRES_AT
CEIM_SERVICE_URL
COMPANION_LLM_ENABLED
COMPANION_RETRIEVAL_TIMEOUT_SECONDS
DATA_CATALOG_URL
DATA_JOB_APPROVAL_TOKEN
DATA_JOB_APPROVAL_TOKEN_ACTOR
DATA_JOB_APPROVAL_TOKEN_EXPIRES_AT
DATA_JOB_EXECUTION_TOKEN
DATA_JOB_EXECUTION_TOKEN_ACTOR
DATA_JOB_EXECUTION_TOKEN_EXPIRES_AT
DATA_PIPELINE_SERVICE_URL
DATA_PRODUCT_APPROVAL_TOKEN
DATA_PRODUCT_APPROVAL_TOKEN_ACTOR
DATA_PRODUCT_APPROVAL_TOKEN_EXPIRES_AT
DATA_PRODUCT_SERVICE_URL
DEPO_ALLOW_INSECURE_LOCAL_AUTH
DEPO_APIM_SUBSCRIPTION_KEY
DEPO_API_GATEWAY_URL
DEPO_CEIM_IDENTITY_MODE
DEPO_CREDENTIAL_STORE
DEPO_DATABASE_SCHEMA
DEPO_DATABASE_URL
DEPO_FRONTEND_HOST
DEPO_FRONTEND_PORT
DEPO_GATEWAY_AGENTIC_PATH
DEPO_GATEWAY_CATALOG_PATH
DEPO_GATEWAY_CEIM_PATH
DEPO_GATEWAY_DATA_PIPELINE_PATH
DEPO_GATEWAY_DATA_PRODUCT_PATH
DEPO_GATEWAY_GRAPH_PATH
DEPO_GATEWAY_INGESTION_PATH
DEPO_GATEWAY_ONTOLOGY_PATH
DEPO_GATEWAY_OSLC_PATH
DEPO_GATEWAY_QIF_PATH
DEPO_HADOOP_HOME
DEPO_IIF_ADAPTER_SECURITY_ENABLED
DEPO_IIF_ADAPTER_TOKEN
DEPO_IIF_MAX_UPLOAD_BYTES
DEPO_IIF_RUNTIME_ROOT
DEPO_IIF_UPLOAD_DIR
DEPO_IIF_WORKFLOW_DIR
DEPO_JAVA_HOME
DEPO_LOCAL_SERVICE_HOST
DEPO_MAX_INGEST_BYTES
DEPO_PIPELINE_EXECUTION_MODE
DEPO_PIPELINE_LEASE_SECONDS
DEPO_PIPELINE_POLL_SECONDS
DEPO_PIPELINE_SCHEDULER_ENABLED
DEPO_PIPELINE_WORKER_STALE_SECONDS
DEPO_POSTGRES_BIN_DIR
DEPO_POSTGRES_CONNECT_TIMEOUT_SECONDS
DEPO_POSTGRES_DATA_DIR
DEPO_POSTGRES_MODE
DEPO_POSTGRES_SERVICE_NAME
DEPO_PROJECT_ID
DEPO_REQUIRE_TOKEN_ACTOR
DEPO_ROUTING_MODE
DEPO_SERVICE_HOST
DEPO_SPARK_ENABLED
DEPO_SPARK_HOME
DEPO_SPARK_MASTER
DEPO_SPARK_NEO4J_ENABLED
DEPO_SPARK_NEO4J_PACKAGE
DEPO_SPARK_OUTPUT_ROOT
DEPO_SPARK_POSTGRES_DRIVER_JAR
DEPO_SPARK_POSTGRES_ENABLED
DEPO_TENANT_ID
DEPO_TOKEN_EXPIRES_AT
DEPO_TRUSTED_GATEWAY_IPS
DOCUMENT_EASYOCR_ALLOW_DOWNLOAD
DOCUMENT_EASYOCR_MODEL_DIR
DOCUMENT_MAX_OCR_PAGES
DOCUMENT_OCR_GPU
DOCUMENT_OCR_LANGUAGES
DOCUMENT_OCR_PROVIDER
DT_AGENT_ENABLED
DT_AGENT_GATEWAY_TOKEN
DT_AGENT_GATEWAY_URL
EMBED_MODEL_NAME
GRAPH_PUBLICATION_TIMEOUT_SECONDS
GRAPH_PUBLICATION_TOKEN
GRAPH_PUBLICATION_TOKEN_ACTOR
GRAPH_PUBLICATION_TOKEN_EXPIRES_AT
GRAPH_READ_TOKEN
GRAPH_READ_TOKEN_ACTOR
GRAPH_READ_TOKEN_EXPIRES_AT
GRAPH_SERVICE_URL
INGESTION_SERVICE_URL
INGESTION_WRITE_TOKEN
INGESTION_WRITE_TOKEN_ACTOR
INGESTION_WRITE_TOKEN_EXPIRES_AT
LLM_MODEL_NAME
LLM_REQUEST_TIMEOUT_SECONDS
NEO4J_AUTH_MODE
NEO4J_DATABASE
NEO4J_ENCRYPTED
NEO4J_MCP_ALLOWED_TOOLS
NEO4J_MCP_ALLOW_WRITES
NEO4J_MCP_ARGS_JSON
NEO4J_MCP_COMMAND
NEO4J_MCP_ENABLED
NEO4J_MCP_ENV_JSON
NEO4J_MCP_SECURITY_ENABLED
NEO4J_MCP_URL
NEO4J_PASS
NEO4J_TLS_MODE
NEO4J_TLS_VERIFY
NEO4J_URI
NEO4J_USER
OLLAMA_API_KEY
OLLAMA_API_KEY_HEADER
OLLAMA_API_URL
OLLAMA_BASE_URL
OLLAMA_CHAT_API_URL
ONTOLOGY_AGENT_ALLOWED_ROOTS
ONTOLOGY_AGENT_LLM_ENABLED
ONTOLOGY_AGENT_MAX_BYTES
ONTOLOGY_APPROVAL_TOKEN
ONTOLOGY_APPROVAL_TOKEN_ACTOR
ONTOLOGY_APPROVAL_TOKEN_EXPIRES_AT
ONTOLOGY_EXTERNAL_API_BASE_URL
ONTOLOGY_EXTERNAL_API_ENABLED
ONTOLOGY_EXTERNAL_API_TIMEOUT_SECONDS
ONTOLOGY_EXTERNAL_API_TOKEN
ONTOLOGY_EXTERNAL_CONTEXT_SEARCH_PATH
ONTOLOGY_EXTERNAL_REGISTERED_PATH
ONTOLOGY_MAX_UPLOAD_BYTES
ONTOLOGY_SERVICE_URL
OSLC_BASE_URL
OSLC_CLIENT_TIMEOUT_SECONDS
OSLC_REMOTE_BASE_URL
OSLC_REMOTE_ENABLED
OSLC_REMOTE_TOKEN
OSLC_SERVICE_URL
OSLC_TRS_STORE
QIF_SERVICE_URL
REACT_APP_AGENTIC_ENABLED
REACT_APP_AGENTIC_SERVICE_URL
REACT_APP_API_VERSION
REACT_APP_DEBUG
REACT_APP_ENV
REACT_APP_LOG_LEVEL
REACT_APP_REQUEST_TIMEOUT
REACT_APP_SIRIUS_WEB_URL
SPARQL_FEDERATION_APPROVAL_TOKEN
SPARQL_FEDERATION_APPROVAL_TOKEN_ACTOR
SPARQL_FEDERATION_APPROVAL_TOKEN_EXPIRES_AT
SPEED_EVENT_TOKEN
SPEED_EVENT_TOKEN_ACTOR
SPEED_EVENT_TOKEN_EXPIRES_AT
SPEED_PATH_APPROVAL_TOKEN
SPEED_PATH_APPROVAL_TOKEN_ACTOR
SPEED_PATH_APPROVAL_TOKEN_EXPIRES_AT
USE_EMBEDDER
USE_LLM
VITE_AGENTIC_SERVICE_URL
VITE_API_GATEWAY_URL
VITE_BACKEND_URL
VITE_CATALOG_SERVICE_URL
VITE_CEIM_SERVICE_URL
VITE_DATA_PIPELINE_SERVICE_URL
VITE_DATA_PRODUCT_SERVICE_URL
VITE_GRAPH_SERVICE_URL
VITE_INGESTION_SERVICE_URL
VITE_ONTOLOGY_SERVICE_URL
VITE_OSLC_SERVICE_URL
VITE_QIF_SERVICE_URL
VOCABULARY_APPROVAL_TOKEN
VOCABULARY_APPROVAL_TOKEN_ACTOR
VOCABULARY_APPROVAL_TOKEN_EXPIRES_AT
