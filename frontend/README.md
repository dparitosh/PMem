# DEPO Frontend

The frontend is a React/Vite single-page application using Siemens IX
components. It communicates with the standalone DEPO service topology rather
than the retired aggregate backend on port 8000.

## Development

Use Node.js 24+ and npm 10+.

```powershell
cd D:\Githuv_repo\PMem\frontend
npm ci
npm run dev
```

Create a production bundle with `npm run build`.

## Service configuration

Vite environment variables use the `VITE_` prefix. Configure either a single
gateway or explicit service URLs:

```env
VITE_API_GATEWAY_URL=https://<gateway-host>
# or, for local service development
VITE_ONTOLOGY_SERVICE_URL=http://127.0.0.1:8011
VITE_GRAPH_SERVICE_URL=http://127.0.0.1:8013
VITE_INGESTION_SERVICE_URL=http://127.0.0.1:8014
VITE_AGENTIC_SERVICE_URL=http://127.0.0.1:8012
VITE_AGENTIC_ENABLED=true
```

Do not use `VITE_ADMIN_API_KEY` as a production secret. Browser variables are
compiled into the client bundle. Keep destructive operations behind the gateway
and server-side authorization.

For supported customer configuration and service startup, use
[../infra/deployment/README.md](../infra/deployment/README.md).
