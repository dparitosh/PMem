# Azure API Management registration

## Ollama model discovery and generation

The DEPO service registration script below does not register Ollama. Configure
its APIM API separately. A `route_missing` diagnostic reports that model
discovery returned HTTP 404; it does not establish whether generation works.
Use APIM's Test trace to distinguish an unmatched frontend operation from a
404 returned by the configured backend.

An importable native Ollama contract is supplied in
`infra/azure-apim/ollama.openapi.json`. For a new API, use suffix `ollama` and
the private Ollama backend root, for example `http://<ollama-private-host>:11434`.
Do not append `/ollama` or `/api` to that backend root unless the actual backend
proxy requires that prefix. The operation path already includes `/api`.

```powershell
az apim api import `
  --resource-group "<resource-group>" `
  --service-name "<apim-name>" `
  --api-id "<ollama-api-id>" `
  --path "ollama" `
  --display-name "Ollama" `
  --service-url "http://<ollama-private-host>:11434" `
  --specification-format OpenApiJson `
  --specification-path ".\infra\azure-apim\ollama.openapi.json" `
  --protocols https `
  --subscription-required true
```

For an existing API, review its operations and policies first. Importing into
its API ID updates that API; do not replace a custom gateway contract blindly.
Add or repair the missing `GET /api/tags` operation if generation already works.
Required native routes are `GET /api/tags` for discovery, `POST /api/chat` for
chat and tool proposals, and `POST /api/generate` if a generate operation is
configured. Embedding clients use `/api/embed` or legacy `/api/embeddings`.

Keep streaming forwarding unbuffered for chat/generate routes. Preserve native
Ollama request and response JSON shapes. The provided contract does not add
authentication policies, configure backend credentials or provision models.
Attach the appropriate APIM product/subscription and existing security policies.

Server configuration for this topology:

```dotenv
OLLAMA_BASE_URL=https://<apim-name>.azure-api.net/ollama
OLLAMA_CHAT_API_URL=https://<apim-name>.azure-api.net/ollama/api/chat
LLM_MODEL_NAME=llama3:latest
OLLAMA_API_KEY=<server-side-secret>
OLLAMA_API_KEY_HEADER=Ocp-Apim-Subscription-Key
```

Use `Ocp-Apim-Subscription-Key` only when the key is an APIM subscription key
and APIM uses that default header. Keep `api-key` when an existing custom
policy or backend explicitly accepts it. The application does not translate
between those authentication contracts. Use HTTPS on the public gateway so
the configured key is not sent over plaintext HTTP.

From the application VM, verify the model-list route returns an Ollama JSON
`models` array containing the exact configured model. Then separately test
the configured generation operation with `stream=false` and a small prompt;
test streaming and tool proposals independently if those features are used.
For 404s, check API suffix, operation method/path, backend base and rewrite
policy in the APIM trace. For 401/403s, check the product subscription and
configured header. Restart the affected services after environment changes.

References: [APIM operation exposure](https://learn.microsoft.com/en-us/azure/api-management/add-api-manually)
and [Ollama native API](https://github.com/ollama/ollama/blob/main/docs/api.md).

Azure API Management (APIM) is the only public entry point for the DEPO
microservices. Keep service URLs private (VNet/private endpoint) and register
their OpenAPI documents through APIM.

```powershell
az login
.\infra\azure-apim\register-depo-apis.ps1 `
  -ResourceGroup "<resource-group>" `
  -SubscriptionId "<subscription-id>" `
  -ApimServiceName "<apim-name>" `
  -OntologyServiceUrl "https://ontology.internal.example" `
  -GraphServiceUrl "https://graph.internal.example" `
  -IngestionServiceUrl "https://ingestion.internal.example" `
  -OslcServiceUrl "https://oslc.internal.example" `
  -QifServiceUrl "https://qif.internal.example" `
  -AgenticServiceUrl "https://agentic.internal.example" `
  -CatalogServiceUrl "https://catalog.internal.example" `
  -DataProductsServiceUrl "https://data-products.internal.example" `
  -CeimServiceUrl "https://ceim.internal.example" `
  -DataPipelineServiceUrl "https://data-pipeline.internal.example"
```

Registered OpenAPI APIM paths include `/ontology`, `/graph`, `/ingestion`,
`/oslc`, `/qif`, `/agentic`, `/catalog`, `/data-products`, `/ceim`, and
`/data-pipeline`; matching OData
paths use the `-odata` suffix. Each service publishes `/odata`,
`/odata/$metadata`, and a read-only `ServiceCapabilities` entity set. The
OData catalog is intentionally a discovery contract; governed domain commands
continue to use OpenAPI.

The script imports OpenAPI through Azure CLI and uses Azure Resource Manager's
native `odata-link` API import for OData metadata. It sets an APIM backend
service URL and never stores database, OSLC, or cloud credentials in source.
HTTPS service URLs and APIM subscriptions are required by default. Only pass
`-AllowAnonymous` for a deliberately bearer-token-only or private-gateway
deployment.

Grant the deployment identity APIM API Contributor (or an equivalent scoped
role) before running the script. Azure CLI supports importing an API with an
OpenAPI specification URL and backend service URL. [Microsoft Learn](https://learn.microsoft.com/en-gb/cli/azure/apim/api?view=azure-cli-latest)

## Apply gateway security policies

After API registration, apply a single, consistent policy to every OpenAPI and
OData API. It validates Microsoft Entra ID bearer tokens against the supplied
OpenID Connect document and applies a per-subscription/IP rate limit.

```powershell
.\infra\azure-apim\register-depo-policies.ps1 `
  -SubscriptionId "<subscription-id>" `
  -ResourceGroup "<resource-group>" `
  -ApimServiceName "<apim-name>" `
  -OpenIdConfigUrl "https://login.microsoftonline.com/<tenant-id>/v2.0/.well-known/openid-configuration" `
  -Audience "api://<depo-api-app-id>"
```

Keep every backend private behind APIM (private endpoint/VNet integration),
and configure APIM-to-backend mTLS or managed identity according to the target
hosting platform. Those credentials and certificate identifiers deliberately
remain deployment configuration, never source code.

## Validate service contracts before registration

Run this from the same private network that APIM uses to reach the services.
It verifies liveness, OpenAPI, and OData metadata before import.

```powershell
.\infra\azure-apim\test-depo-service-contracts.ps1 `
  -OntologyServiceUrl "https://ontology.internal.example" `
  -GraphServiceUrl "https://graph.internal.example" `
  -IngestionServiceUrl "https://ingestion.internal.example" `
  -OslcServiceUrl "https://oslc.internal.example" `
  -QifServiceUrl "https://qif.internal.example" `
  -AgenticServiceUrl "https://agentic.internal.example" `
  -CatalogServiceUrl "https://catalog.internal.example" `
  -DataProductsServiceUrl "https://data-products.internal.example" `
  -CeimServiceUrl "https://ceim.internal.example" `
  -DataPipelineServiceUrl "https://data-pipeline.internal.example"
```
