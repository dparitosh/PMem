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
  -RequireSubscription
```

Registered OpenAPI APIM paths are `/ontology`, `/graph`, `/ingestion`, and
`/oslc`. Registered OData v4 paths are `/ontology-odata`, `/graph-odata`,
`/ingestion-odata`, and `/oslc-odata`. Each service publishes `/odata`,
`/odata/$metadata`, and a read-only `ServiceCapabilities` entity set. The
OData catalog is intentionally a discovery contract; governed domain commands
continue to use OpenAPI.

The script imports OpenAPI through Azure CLI and uses Azure Resource Manager's
native `odata-link` API import for OData metadata. It sets an APIM backend
service URL and never stores database, OSLC, or cloud credentials in source.

Grant the deployment identity APIM API Contributor (or an equivalent scoped
role) before running the script. Azure CLI supports importing an API with an
OpenAPI specification URL and backend service URL. [Microsoft Learn](https://learn.microsoft.com/en-gb/cli/azure/apim/api?view=azure-cli-latest)
