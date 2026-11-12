# Nexus API gateway setup (Azure API Management)

Use this procedure only when choosing `DEPO_ROUTING_MODE=gateway`. A local workstation installation needs no Azure gateway, Azure subscription or APIM subscription key. Setup and update scripts install Nexus; they do not provision APIM, create products/subscriptions or issue gateway keys.

## 1. Identify the addresses and credentials

| Item | Example / where to obtain it |
| --- | --- |
| Frontend URL | `https://nexus.example.com/`; supplied by the frontend/reverse-proxy administrator. |
| API gateway base | `https://customer-nexus.azure-api.net`; copy the **Gateway URL** from your APIM instance's Overview. A custom gateway hostname may replace it. |
| Ontology API | `<gateway-base>/ontology/api/v1/ontologies`; generated from the base and service suffix. |
| Azure subscription ID | Resource/billing subscription GUID used by Azure CLI; not an API key. |
| APIM subscription key | Primary or secondary key of an active APIM API/product subscription; obtain in step 4. |
| Nexus application credentials | Existing root `.env.local` profiles and delegated browser sessions; independent of the APIM key. |
| LLM gateway | Optional `OLLAMA_BASE_URL`, AOI or provider configuration; it is not `DEPO_API_GATEWAY_URL`. |

Do not use the developer portal URL, Azure management URL, frontend URL, `/ollama`, `/ontology` or `/api/v1` as the gateway base. The supplied import script creates service suffixes directly below the gateway host. Add `/depo` to the base only if your gateway administrator actually configured that shared prefix for every service; the default import script does not create it.

## 2. Prepare APIM and private connectivity

The Azure administrator provisions an API Management instance with networking appropriate for the deployment, DNS/TLS and access to the application backends. Give the deployment identity the approved API-management permissions. On the deployment workstation install Azure CLI and run `az login`.

Nexus's native APIs listen on ports 8010–8019. The import script requires HTTPS service URLs, for example `https://ontology.internal.example`. Provide private TLS ingress/reverse-proxy endpoints to the native listeners. A loopback listener is usable only by a proxy on the same machine. Azure-hosted APIM cannot reach `127.0.0.1` on the application server, and a private address is not reachable without the required network path. Verify APIM can reach the backend as well as the import/control-plane environment's access to the OpenAPI and OData metadata URLs.

Bootstrap the application privately in local/token mode first using [INSTALLATION.md](../../INSTALLATION.md). Confirm private readiness before exposing the gateway. Existing customer gateways should use reviewed API revisions and preserve their custom policies.

## 3. Register the APIs

From the repository root, substitute your ten private HTTPS endpoints:

```powershell
$registration = @{
  ResourceGroup='customer-rg'
  SubscriptionId='YOUR-AZURE-SUBSCRIPTION-GUID'
  ApimServiceName='customer-nexus'
  QifServiceUrl='https://qif.internal.example'
  OntologyServiceUrl='https://ontology.internal.example'
  AgenticServiceUrl='https://agentic.internal.example'
  GraphServiceUrl='https://graph.internal.example'
  IngestionServiceUrl='https://ingestion.internal.example'
  OslcServiceUrl='https://oslc.internal.example'
  CatalogServiceUrl='https://catalog.internal.example'
  DataProductsServiceUrl='https://products.internal.example'
  CeimServiceUrl='https://ceim.internal.example'
  DataPipelineServiceUrl='https://pipeline.internal.example'
}
& .\infra\azure-apim\register-depo-apis.ps1 @registration
```

The script selects the specified Azure subscription and stops on a failed CLI operation. It imports ten OpenAPI APIs and ten OData APIs; it does not create their backends. It uses IDs `depo-<manifest-service-id>` and `depo-<manifest-service-id>-odata`. The schema-set service ID is `schema-sets`, while its public suffix is `qif`.

| Service suffix | Native port | Example API path after gateway suffix |
| --- | ---: | --- |
| qif | 8010 | /api/v1/qif |
| ontology | 8011 | /api/v1/ontologies |
| agentic | 8012 | /api/v1/chat |
| graph | 8013 | /api/v1/graph |
| ingestion | 8014 | /api/v1/import/tasks |
| oslc | 8015 | /oslc |
| catalog | 8016 | /api/v1/catalog |
| data-products | 8017 | /api/v1/data-products |
| ceim | 8018 | /api/v1 |
| data-pipeline | 8019 | /api/v1/pipeline |

The imported OpenAPI is authoritative for operations; the examples above identify route families, not guaranteed list endpoints. OData uses a separate `<suffix>-odata` API.

## 4. Create a product and obtain a subscription key

In Azure Portal, open the intended APIM instance. Create a product for Nexus access and add all ten imported Nexus APIs that the client must use, plus their OData APIs if needed. Publish the product and require subscriptions. Under **APIs → Subscriptions → Add subscription**, create a subscription scoped to that product and ensure it is active. Open that subscription to obtain its primary or secondary key; keep it in your approved secret store. Consumers may instead request access through the configured developer portal or receive the key from the API publisher. See [Microsoft's subscription procedure](https://learn.microsoft.com/en-us/azure/api-management/api-management-howto-create-subscriptions).

One product subscription works only for APIs included in that product. A key scoped solely to Ontology will not authorize the other service APIs. Do not distribute an all-access administrative subscription as the normal client credential. Nexus cannot generate, recover or derive this key from an application key or Azure subscription ID.

## 5. Configure policies for the chosen authentication mode

For the default **`AUTH_MODE=token`**, preserve `Authorization` and `X-API-Key` through APIM. APIM checks `Ocp-Apim-Subscription-Key`; Nexus independently checks its registered credentials/delegated session. Do not run `register-depo-policies.ps1` for this mode: it installs Entra JWT validation, which rejects Nexus opaque session tokens.

For an intentionally designed **Entra** deployment, use the Entra policy helper only after configuring issuer/audience, backend trusted gateway IPs and approved roles. The helper replaces API policies; merge customer CORS, routing and other policies deliberately. Current durable agent worker mode requires token authentication; Entra is a separate deployment qualification, not a drop-in change to the default setup.

If frontend and API origins differ, configure CORS at API or global scope for the exact frontend origin, not only at product scope. Allow the methods in the imported contracts and the headers actually used: `Authorization`, `Content-Type`, `X-API-Key`, `Ocp-Apim-Subscription-Key`, `Idempotency-Key` and `X-Request-ID`. Expose session, request/run identity and download headers required by the application. Verify unauthenticated OPTIONS preflight; browser preflight does not supply the product key. Check inherited policy order. See [Microsoft's CORS policy guidance](https://learn.microsoft.com/en-us/azure/api-management/cors-policy).

At the API/global inbound policy, adapt this CORS fragment to the actual frontend origin. Merge it with existing policies and retain exactly one effective CORS policy; it is not a replacement for authentication:

```xml
<cors allow-credentials="false">
  <allowed-origins><origin>https://nexus.example.com</origin></allowed-origins>
  <allowed-methods preflight-result-max-age="300">
    <method>GET</method><method>POST</method><method>PUT</method>
    <method>PATCH</method><method>DELETE</method><method>HEAD</method><method>OPTIONS</method>
  </allowed-methods>
  <allowed-headers>
    <header>Authorization</header><header>Content-Type</header><header>X-API-Key</header>
    <header>Ocp-Apim-Subscription-Key</header><header>Configuration-Context</header>
    <header>X-Request-ID</header><header>X-Session-ID</header><header>Idempotency-Key</header>
  </allowed-headers>
  <expose-headers>
    <header>Content-Disposition</header><header>X-Request-ID</header>
    <header>X-Session-ID</header><header>X-Session-Expires-At</header>
    <header>X-DEPO-Run-ID</header><header>X-DEPO-Run-Kind</header>
    <header>X-DEPO-Cleanup-ID</header><header>OData-Version</header>
  </expose-headers>
</cors>
```

The default token client uses headers, not cross-origin cookies. A customer cookie-based proxy needs a separate reviewed credentialed-origin policy. Preserve `Configuration-Context` when using OSLC configurations.

For streaming routes, configure APIM's effective backend forwarding with `buffer-response="false"` and an approved bounded timeout; test SSE/NDJSON end to end. Do not replace or duplicate an existing `forward-request` blindly. Gateway policy, upload limits and backend deadlines must support the chosen workloads.

## 6. Configure Nexus and switch routing

Edit the existing **root** `.env.local` privately:

```dotenv
AUTH_MODE=token
DEPO_CREDENTIAL_STORE=postgres
DEPO_ROUTING_MODE=gateway
DEPO_API_GATEWAY_URL=https://customer-nexus.azure-api.net
DEPO_APIM_SUBSCRIPTION_KEY=YOUR-ACTIVE-APIM-SUBSCRIPTION-KEY
```

Keep existing database settings and application credentials. Keep `DEPO_SERVICE_HOST` set for the actual listener/proxy topology; changing the gateway URL does not change listener binding. Do not copy keys into `frontend/.env.local`, `VITE_*`, command history, screenshots or tickets. If custom service suffixes are used, configure the corresponding `DEPO_GATEWAY_<SERVICE>_PATH` overrides; exclude `/api/v1` from suffix overrides. See [Configuration guide](CONFIGURATION.md).

From the repository root, run `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\update-depo.ps1`. The normal update preserves configuration, applies pending schema migrations, builds and restarts. It does not update APIM. Connect the browser through Admin API access with the configured gateway subscription and application access. A server-side APIM key does not automatically provision a browser session or insert a key into browser build variables. Where browser-readable gateway keys are prohibited, use an approved same-origin backend proxy instead.

## 7. Verify and maintain

For token/PostgreSQL deployments run:

```powershell
& .\infra\windows\test-depo-browser-session.ps1 -EnvFile .\.env.local -Gateway
```

This checks temporary read-only delegated access without printing keys. Test from the actual remote browser as well: login, ontology list, retained job status, approved worker execution, download, reconnect and streaming. A portal test alone does not establish browser CORS or session validity. After code upgrades, reimport changed OpenAPI contracts, review policies/product membership, and repeat checks.

| Failure | First check |
| --- | --- |
| No response / timeout | DNS/TLS, frontend route, APIM private connectivity and listener/proxy binding. |
| APIM invalid subscription | Active product subscription, API membership and subscription header. |
| Nexus 401/403 | Application/session credential validity and forwarded headers; an APIM key alone is insufficient. |
| 404 | Gateway base/suffix and imported operation; inspect APIM trace to locate gateway versus backend rejection. |
| CORS / empty preflight response | Exact origin, effective policy scope/order and allowed headers. |
| Streaming arrives all at once | APIM/proxy buffering, timeouts and compression policy. |

This runbook does not certify an untested customer APIM environment. No Azure resource or policy is changed by the local Nexus installer.
