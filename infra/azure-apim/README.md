# Azure API Management registration

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
  -DataProductsServiceUrl "https://data-products.internal.example"
```

Registered OpenAPI APIM paths include `/ontology`, `/graph`, `/ingestion`,
`/oslc`, `/qif`, `/agentic`, `/catalog`, and `/data-products`; matching OData
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
  -DataProductsServiceUrl "https://data-products.internal.example"
```
