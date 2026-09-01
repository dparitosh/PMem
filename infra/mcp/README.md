# Semantica MCP client registration

Copy the `depo-semantica` entry from `semantica-mcp.json` into the selected
MCP client's local configuration. Set `SEMANTICA_KG_PATH` to a persistent,
service-owned graph location and use the same Python environment in which
Semantica is installed.

This is an explicit stdio registration. Do not expose the MCP process as an
unauthenticated public HTTP endpoint; external access must pass through the
authenticated APIM APIs.
