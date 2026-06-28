# DEPO Frontend

React frontend for the DEPO application.

## What The UI Covers

- graph explorer
- ontology junction / ontology workflows
- semantic bridge
- import workflows
- recommendations
- reports
- chat / knowledge companion

## Start The Frontend

From repository root:

```bat
.\start_frontend.bat
```

Or directly:

```bat
cd D:\Depo_Onto_Engine\frontend
npm start
```

## Default URL

- `http://localhost:3000`

## Backend Dependency

The frontend expects the backend API to be available, normally at:
- `http://localhost:8000`

For LAN / VM / IP-based use, configure the backend URL before startup.

Example:

```bat
set APP_HOST=192.168.1.50
.\start_backend.bat
.\start_frontend.bat
```

## Customer Release Note

This frontend is the main customer-facing UI.

The standalone ontology agentic service in `standalone/ontology_agentic_service/` is a separate companion service and is not a replacement for this UI.
