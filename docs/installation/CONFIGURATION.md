# Nexus deployment configuration

Use this with [customer installation](../../INSTALLATION.md). The existing `.env.local` is authoritative; preserve it during upgrades. Never replace customer secrets with a template or use `configure-depo.ps1 -Force` as an upgrade step.

Optional evaluation data is separate from infrastructure configuration. The [Engineering ODS toolkit](../../standalone/engineering_ods/README.md) takes service URLs and token **environment-variable names** in its own JSON file. Never copy customer token values, `.env.local` or registration receipts into the toolkit archive. PostgreSQL/Neo4j passwords are not required by the API loader.

## Choose the deployment path first

| Scenario | Routing mode | Gateway URL / subscription key |
| --- | --- | --- |
| One workstation, browser on that machine | `local` | Leave both empty. No APIM setup is needed. |
| Private LAN, clients can reach each service | `local` | No APIM key. Configure reachable listeners, allowed frontend origins and network rules deliberately. |
| Remote browsers through APIM | `gateway` | Set the actual APIM gateway base; obtain a product subscription key separately. Follow [API gateway setup](API_GATEWAY_SETUP.md). |
| Customer reverse proxy | Depends on actual route topology | Use the configured proxy base/suffixes. A non-APIM proxy does not issue Azure subscription keys. |

For a first installation, guided `Setup-DEPO.cmd` is the normal entry point. Advanced `configure-depo.ps1` creates root and frontend configuration without installing the application. `-GatewayUrl https://customer-nexus.azure-api.net` now sets root gateway routing as well as the public browser URL; it does not create the gateway or a key. Bootstrap private backend readiness and register the gateway before treating gateway-mode installation as complete.

## Settings and ownership

| Root `.env.local` setting | Meaning |
| --- | --- |
| `DEPO_ROUTING_MODE` | `local` derives per-service addresses; `gateway` derives gateway suffixes. |
| `DEPO_SERVICE_HOST` | Address the backend processes bind to; independent of the public gateway URL. A process listening only on 127.0.0.1 is inaccessible directly from another machine. |
| `DEPO_LOCAL_SERVICE_HOST` | Optional reachable local-mode host override. Never use 0.0.0.0 as a browser destination. |
| `DEPO_FRONTEND_HOST` | Frontend listener; not the public API endpoint. |
| `DEPO_API_GATEWAY_URL` | Gateway base, normally `https://<apim-name>.azure-api.net`, without service suffix or `/api/v1`. |
| `DEPO_APIM_SUBSCRIPTION_KEY` | Server-side APIM subscription credential. Leave empty in local mode or when the chosen proxy does not require one. |
| `DEPO_GATEWAY_<SERVICE>_PATH` | Optional custom suffix, e.g. `DEPO_GATEWAY_GRAPH_PATH=engineering/graph`; no `/api/v1`. Default suffixes match `services.json`. |
| `AUTH_MODE` | Default `token`; routing and authentication are separate choices. APIM does not require changing this to Entra. |
| `DEPO_CREDENTIAL_STORE` | Default `postgres`; application profiles/sessions are independently enforced behind APIM. |
| `DEPO_DATABASE_URL`, `DEPO_DATABASE_SCHEMA` | Application/reporting database and schema; preserve during upgrades. |
| `NEO4J_URI`, database/user/password settings | Graph connection; use the supported names in the template and avoid conflicting aliases. |
| `ARTIFACT_STORAGE` | Absolute durable directory; preserve alongside database backups. |
| `USE_LLM`, provider/model/key settings | AI provider configuration; independent of Nexus API routing. |

`frontend/.env.local` contains public settings only. Never put keys/passwords in `VITE_*` or `REACT_APP_*`. Root runtime routing takes precedence over older browser URL overrides; after changing root routing, restart the frontend launcher. Rebuild after source updates through the normal installer/updater. The frontend's Admin API access connection is separate from server configuration: follow its gateway subscription/application credential prompts when applicable.

## Examples (edit the existing root file privately)

Local workstation:

```dotenv
AUTH_MODE=token
DEPO_ROUTING_MODE=local
DEPO_SERVICE_HOST=127.0.0.1
DEPO_API_GATEWAY_URL=
DEPO_APIM_SUBSCRIPTION_KEY=
```

APIM after its APIs, connectivity and subscription are ready:

```dotenv
AUTH_MODE=token
DEPO_ROUTING_MODE=gateway
DEPO_API_GATEWAY_URL=https://customer-nexus.azure-api.net
DEPO_APIM_SUBSCRIPTION_KEY=YOUR-ACTIVE-PRODUCT-SUBSCRIPTION-KEY
```

Keep the actual private listener, database and application credential settings; the gateway example does not replace them. A key from an Ollama API subscription may have no access to Nexus APIs. Azure subscription GUID, APIM product key and application Admin key are three different values.

## Change and verify

1. Back up both configuration files and durable application data. Edit only the intended settings.
2. For a code/schema upgrade, run the repository-root `update-depo.ps1`; guided Setup is also supported. Existing configuration and records are retained. Use `configure-depo.ps1 -CheckExisting` for a read-only template comparison, not `-Force`.
3. The installer starts ten APIs and three workers. Gateway APIs, TLS proxies, subscriptions and product membership are separate infrastructure tasks; reimport changed OpenAPI after an application upgrade.
4. Token/PostgreSQL authentication: run `infra/windows/test-depo-browser-session.ps1 -EnvFile .env.local`; add `-Gateway` only for a configured gateway deployment.
5. Test from the intended client network: connect access, open an ontology, inspect a retained run, reconnect, download evidence and exercise streaming. Installation success alone does not establish customer gateway acceptance.

For missing optional settings, `configure-depo.ps1 -UpdateMissing` preserves existing values while adding template defaults; review those defaults before running features. It neither creates cloud infrastructure nor replaces existing keys.


## Customer sandbox: Ollama and Engineering ODS acceptance

Install the complete reviewed customer ZIP using [the installation runbook](../../INSTALLATION.md); do not copy a workstation virtual environment, `.env.local`, runtime IDs or publication receipts. Provision PostgreSQL/Neo4j first. Keep the independent [ODS toolkit](../../standalone/engineering_ods/README.md) outside the application directory. Setup/upgrade do not install Ollama, download models or publish demo data.

1. Install/start the approved local Ollama server. Run `ollama list`; select exact installed generation and embedding tags. The model must pass structured-output checks for the default agent proposal mode. Native tool calling is a separate capability.
2. Edit the existing root `.env.local` privately, retaining customer database connections, artifact storage and credentials:

```dotenv
USE_LLM=ollama
USE_EMBEDDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_API_URL=
OLLAMA_CHAT_API_URL=
OLLAMA_API_KEY=
OLLAMA_DISCOVERY_ENABLED=true
OLLAMA_PROPOSAL_MODE=structured
COMPANION_LLM_ENABLED=true
ONTOLOGY_AGENT_LLM_ENABLED=true
```

Set `LLM_MODEL_NAME` and `EMBED_MODEL_NAME` to the installed tags. Set `AGENTIC_MODEL_CONTEXT_TOKENS` to the verified allocated Ollama context; this application setting bounds requests but does **not** configure the Ollama server. Configure the server context separately and inspect `ollama ps` after loading the model. Do not assume the template's 32768-token budget is available on the customer machine. Keep `DT_AGENT_ENABLED=false` unless integrating an external DT execution gateway; it is not the local Ollama enablement switch. Optional `AGENT_MEMORY_ENABLED` controls graph-native conversation/mapping memory, not the existence of published historical engineering facts or PostgreSQL saved conversations. Assign customer-specific tenant/project/memory scope.

For a remote Ollama server use the approved HTTPS endpoint and `OLLAMA_REQUIRE_HTTPS=true`; set this flag to false for native local HTTP. Do not retain stale cloud/alternate Ollama route overrides. No OpenAI key or API gateway subscription is needed for native local Ollama.

3. From the release root, run the explicit inference diagnostics (bounded test prompts, no business tools executed):

```powershell
& '.\infra\windows\test-depo-ollama.ps1' -EnvFile '.env.local' -ProbeGeneration -ProbeChat -ProbeEmbeddings -ProbeProposal
& '.\manage-depo.ps1' -Action Restart -EnvFile '.env.local'
& '.\infra\windows\test-depo-browser-session.ps1' -EnvFile '.env.local'
```

Require each requested capability to pass. Model discovery alone is not agent readiness. Use Agent Control's explicit model capability probe before selecting native tool mode. Measure response time with the real evidence prompts on customer hardware.

4. Generate a new ODS artifact using customer-specific namespace/output settings; register, review and publish through the toolkit's explicit CR/CO stages. Use fresh IDs returned by that installation. Run `verify` and require exit 0 before opening the scenario.
5. Run the toolkit acceptance questions in Recommendations and Companion. Expand Evidence and supporting graph. Confirm historical option dispositions, current B evaluation, source identity and selected ontology. Ask the same-context follow-up, then inspect the saved turn in Memory insights. A past selection is not current authorization.
6. To demonstrate PostgreSQL ODS/analytics, complete the toolkit README's graph snapshot → semantic preparation → business mart → central product publication steps. Check units, source IRIs, immutable dataset/configuration and catalog delivery. Registering Turtle alone does not create those tables or a published product.

The bundled 45-record scenario reproduces the historical/current bearing decision story. It does not bundle the later 1,000-row attached inspection workbook, its conflicting plan limits, retained SWRL assessment or an already published analytics mart. Those require separately reviewed source artifacts and governed ingestion; do not present them as replicated by this toolkit.

Ollama references: [structured outputs](https://docs.ollama.com/capabilities/structured-outputs), [tool calling](https://docs.ollama.com/capabilities/tool-calling), [allocated context](https://docs.ollama.com/context-length).
