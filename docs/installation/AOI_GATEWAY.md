# Optional AOI adapter: configure from PMem

No Azure APIM or external API gateway is required. PMem connects directly from its backend to the separate AOI Wrapper adapter. The existing `aoi_gateway` module name and `AOI_GATEWAY_TOKEN` setting are retained for compatibility; they identify this adapter, not an APIM service.

Configure the connection in PMem's selected root `.env.local`: `USE_LLM=aoi`, `AOI_BASE_URL`, `AOI_MODEL`, and `AOI_GATEWAY_TOKEN`. These are server settings; the Admin UI does not currently save provider configuration. Restart PMem after changing them. Set `USE_EMBEDDER` explicitly to your existing embedding provider if only chat should use AOI, because an omitted value follows `USE_LLM`. Changing embedding providers requires checking vector dimensions and existing index compatibility.

The adapter's `.env.aoi.local` owns AOI account credentials and vendor deployment settings. PMem's `.env.local` owns the adapter connection and model alias. Model aliases must match the adapter configuration. Neither credentials nor direct adapter access belong in frontend settings.

AOI is an optional backend provider. The default installer does not install or start this gateway. IIF remains unchanged: preparation copies its existing helper and CPython 3.12 wrapper files byte-for-byte into a private directory and records SHA-256 checksums. Vendor files and credentials are not included in Git.

## 1. Prepare a separate runtime

Use CPython 3.12 on the customer machine. From PowerShell, substitute the actual repository and IIF paths throughout:

```powershell
Set-Location -LiteralPath 'E:\App\PMem'
py -3.12 -m venv .aoi_venv
& .\.aoi_venv\Scripts\python.exe -m pip install --require-hashes -r .\backend\aoi_gateway\requirements-win-py312.lock
if ($LASTEXITCODE -ne 0) { throw 'Gateway dependency installation failed' }
& .\.aoi_venv\Scripts\python.exe -m pip check
if ($LASTEXITCODE -ne 0) { throw 'Gateway dependencies are incompatible' }
& .\.aoi_venv\Scripts\python.exe -m backend.aoi_gateway prepare --source 'D:\GenAI_Projects\IIF_DT' --destination 'E:\App\PMem\data\aoi-gateway\vendor'
if ($LASTEXITCODE -ne 0) { throw 'Wrapper preparation failed' }
if (-not (Test-Path -LiteralPath .\.env.aoi.local)) {
    Copy-Item -LiteralPath .\backend\aoi_gateway\gateway.env.example -Destination .\.env.aoi.local
}
notepad.exe .\.env.aoi.local
```

Do not install gateway dependencies into PMem's backend environment or IIF's runtime. The Windows x64 CPython 3.12 lock pins transitive dependencies and selected wheel hashes; dependency resolution was verified without installation. `requirements.in` records the direct dependencies for future reviewed lock regeneration. Other platforms require a separately validated lock. Customer runtime validation remains necessary: successful resolution and offline contract tests do not establish live vendor compatibility.

## 2. Enter customer settings

In `.env.aoi.local`, set the private wrapper-copy directory, AOI username/password, authorized model and deployment names, and embedding dimensions. Sample deployment names must be confirmed with the customer's AOI operator. Generate a random gateway bearer token of at least 32 characters using a password manager. Keep this file private; do not paste its contents into chat or commit it.

The AOI account credentials belong only in this gateway file. PMem uses the gateway token and never sends an AOI username/password in inference requests.

## 3. Start and verify the gateway

```powershell
& .\.aoi_venv\Scripts\python.exe -m backend.aoi_gateway serve --env-file 'E:\App\PMem\.env.aoi.local' --host 127.0.0.1 --port 8020
```

Keep this console running, or configure the customer's approved service manager with this exact command and repository working directory. Restart the gateway after changing its configuration. It is independent of PMem's standard Start/Stop lifecycle.

`GET /healthz` checks HTTP liveness only. Authenticated `GET /readyz` initializes the wrapper and verifies its copied files, but does not verify inference. `/v1/models` lists configured aliases, not tested availability. `/v1/capabilities` reports supported contracts and missing setting names. Authenticated requests use `Authorization: Bearer <gateway token>`; never put the token in a URL.

Bind to loopback when hosted with PMem. A remote gateway requires HTTPS, backend-only network access and a correctly configured reverse proxy. Browser access and CORS are unnecessary.

## 4. Select AOI in PMem

After customer gateway validation, set these values in PMem's selected `.env.local`:

```dotenv
USE_LLM=aoi
AOI_BASE_URL=http://127.0.0.1:8020/v1
AOI_MODEL=aoi-chat
AOI_GATEWAY_TOKEN=<same private gateway token>
OLLAMA_PROPOSAL_MODE=structured
```

Restart PMem using the repository's `manage-depo.ps1 -Action Restart -EnvFile <absolute environment path>` command. Existing authorization, evidence grounding, workflow approvals and memory remain PMem responsibilities. AOI is used for generation; there is no automatic fallback to another cloud provider.

Embeddings are a separate opt-in:

```dotenv
USE_EMBEDDER=aoi
AOI_EMBED_MODEL=aoi-embedding
EMBEDDING_VECTOR_DIMENSIONS=1536
```

The dimension must match the actual AOI deployment and `AOI_EMBEDDING_DIMENSIONS` in the gateway. Do not reuse an incompatible vector index or mix embeddings from different providers. Plan a separate embedding space and re-embedding before switching existing customer data.

## 5. Customer acceptance and troubleshooting

Verify a short generation request, a structured proposal, an embedding batch with the expected dimension, and a grounded Companion answer with source references. Admin model capability probes perform inference and may incur provider usage. Native tool calling, streaming and vision are explicitly unsupported; structured proposals remain available. JSON-object mode validates the generated object after generation and is not native constrained decoding.

The gateway serializes wrapper access. Concurrent requests return HTTP 429; hung initialization/inference is terminated at the configured deadline and returns 504. HTTP 401 indicates the gateway bearer token; 503 indicates missing configuration or failed wrapper initialization; 502 indicates failed or invalid inference; 501 indicates an unsupported capability. Error responses omit vendor exception bodies and account secrets. A completion without a verifiable finish marker remains `unknown` and PMem will not treat it as a complete response.

Customer acceptance is pending until the unchanged wrapper, credentials, deployment permissions, dependency resolution and actual responses are verified in that environment. This integration does not activate AOI or create AOI credentials on the development installation.
