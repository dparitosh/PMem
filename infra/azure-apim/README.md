# Azure API Management registration

Azure API Management (APIM) is the only public entry point for the DEPO
microservices. Keep service URLs private (VNet/private endpoint) and register
their OpenAPI documents through APIM.

```powershell
az login
.\infra\azure-apim\register-depo-apis.ps1 `
  -ResourceGroup "<resource-group>" `
  -ApimServiceName "<apim-name>" `
  -OntologyServiceUrl "https://ontology.internal.example" `
  -GraphServiceUrl "https://graph.internal.example" `
  -IngestionServiceUrl "https://ingestion.internal.example" `
  -OslcServiceUrl "https://oslc.internal.example" `
  -RequireSubscription
```

Registered APIM paths are `/ontology`, `/graph`, `/ingestion`, and `/oslc`.
The registration uses each service's `/openapi.json`, sets an APIM backend
service URL, and never stores database, OSLC, or cloud credentials in source.

Grant the deployment identity APIM API Contributor (or an equivalent scoped
role) before running the script. Azure CLI supports importing an API with an
OpenAPI specification URL and backend service URL. [Microsoft Learn](https://learn.microsoft.com/en-gb/cli/azure/apim/api?view=azure-cli-latest)
