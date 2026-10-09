# Ontology registration review

> Dated audit record: use [the current audit index](README.md) for latest validation and acceptance status. Findings and test counts below belong to their recorded review; they are not a current release certificate.

Native registration: POST /api/v1/ontologies/register on the ontology service (8011); multipart artifact, ontology_name, prefix, optional description/source. Router dependencies require ONTOLOGY_APPROVAL_TOKEN for writes. A successful registration creates a syntax-validated draft, not graph publication. The frontend context reads the native catalog first and uses the historical ingestion registry only as a compatibility fallback.

Fixed defects:

- Generic and engineering ingestion workflows omitted the write credential on protected ontology calls; both now use the explicit server credential and gateway-scoped subscription headers.
- HTTP registration read the entire upload without a bound; it now reads at most limit+1 bytes and returns 413 for oversized requests.
- Synchronous parsing, file operations and PostgreSQL calls blocked the async registration route; registration now runs in the framework thread pool.
- RDF/XML allowed DTD/entity declarations and JSON-LD could fetch remote/imported contexts; input guards reject those before RDF parsing.
- Reserved metadata.json uploads could overwrite the artifact with catalog metadata; reserved and invalid Windows filenames are rejected.
- Empty RDF documents were accepted as ontology artifacts; parsing now requires at least one triple.
- Extra metadata could overwrite identity, paths and lifecycle state; protected fields cannot be replaced.
- A corrupt local metadata mirror could break the whole registry list; invalid mirrors are skipped with a recovery warning and duplicate IDs are suppressed.
- Catalog artifact reads now reject paths outside their ontology directory.

Verification: installation package validation, syntax of changed Python files, and isolated execution of actual input guards passed. Regression tests were added for reserved filenames, protected metadata overrides and unsafe RDF inputs. Full RDF/HTTP/persistence integration tests were not run: rdflib, FastAPI, httpx and pytest are currently uninstalled. No new packages were installed. Customer registration and APIM multipart forwarding still need live verification.
