# Legacy monolith retirement boundary

`backend/main.py` remains a compatibility host for SPA routes that have not
yet moved to standalone services. New backend work must target one of:

- `backend/ontology_service`
- `backend/graph_service`
- `backend/ingestion_service`
- `backend/oslc_service`

Do not delete a legacy route merely because an equivalent service exists.
First migrate its frontend consumer to the corresponding OpenAPI service,
verify the service contract in CI, then remove the route in a separately
reviewable change. This protects existing user workflows during the gradual
cutover.
