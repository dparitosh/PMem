# Legacy monolith retirement boundary

`backend/main.py` remains a compatibility host for routes that have not yet
moved to standalone services. New backend work must target the owning service
listed in `infra/deployment/services.json`; that manifest is the complete and
authoritative production inventory.

Do not delete a legacy route merely because an equivalent service exists.
First migrate its frontend consumer to the corresponding OpenAPI service,
verify the service contract using local tests, then remove the route in a separately
reviewable change. This protects existing user workflows during the gradual
cutover.
