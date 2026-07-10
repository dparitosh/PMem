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

## Node.js Runtime

Use Node.js 20 LTS with npm 10 for customer release builds. The repository includes `.nvmrc` and `.node-version` at the root, and `frontend/package.json` enforces:

```json
"engines": {
  "node": ">=20.11.0 <23",
  "npm": ">=10.2.0"
}
```

After upgrading Node.js, reinstall frontend dependencies:

```bat
cd D:\Depo_Onto_Engine\frontend
npm install
npm run build
```

`start_frontend.bat` now checks Node.js at startup and stops with a clear message if the machine is below Node.js 20.

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

The frontend expects the backend API to be available. By default the launcher
points it at `http://127.0.0.1:8000`, but remote or LAN deployments should use
the checked-in `service-boundaries.env` file or pass an explicit backend URL.

Example:

```bat
set APP_HOST=192.168.1.50
.\start_services.bat
```

For one-file runtime control, copy `service-boundaries.env.example` to
`service-boundaries.env` and edit the service host/port values there.

## Customer Release Note

This frontend is the main customer-facing UI.

The standalone ontology agentic service in `standalone/ontology_agentic_service/` is a separate companion service and is not a replacement for this UI.
