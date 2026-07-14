# DEPO Graph Miner Mendix Widget

Pluggable web widget baseline targeting Mendix 11.12 and the React client. It accepts DEPO common-graph JSON and offers React Flow or D3 rendering.

## Build

```powershell
npm install
npm run build
npm run release
```

The release command creates an `.mpk` widget package. This widget is intentionally `offlineCapable="false"`; DEPO graph data is expected to be obtained through authenticated Mendix microflows or a server-side connector.

## Runtime contract

- `nodesJson`: array of `{ id, label, type, properties?, metadata?, x?, y? }`
- `linksJson`: array of `{ id?, source, target, type, properties?, metadata? }`
- `renderer`: `reactFlow` or `d3`
- `onNodeSelect`: optional modeled action
- `onGraphChange`: optional modeled action

Do not place API credentials in widget properties or browser code. Use Mendix server-side configuration and microflows for DEPO API access.
