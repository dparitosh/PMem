# OSLC domain and resource audit

## Current implementation

The OSLC service is a read-only interoperability facade over the semantic graph.
It exposes an OSLC Service Provider Catalog, Service Provider, query
capabilities, resource shapes, resource details, dictionaries, taxonomies and a
TRS descriptor/base/change log.

| Area | Status | Resources and properties |
| --- | --- | --- |
| OSLC AM | Implemented | `architecture-resources`, mapped to `oslc_am:Resource`; title, description, identifier, service provider and relation are described by a resource shape. |
| OSLC RM | Implemented | `requirements` and `requirement-collections`, mapped to `oslc_rm:Requirement` and `oslc_rm:RequirementCollection`; collection membership uses `oslc_rm:uses`. |
| OSLC CM | Read-only profile | `change-requests`, mapped to `oslc_cm:ChangeRequest`, with title, description, status, service provider and relation properties. |
| OSLC QM | Read-only profile | `test-results` and `test-cases`, mapped to `oslc_qm:TestResult` and `oslc_qm:TestCase`. |
| AP242 | Implemented as a governed semantic domain | Product/PMI/engineering resources are exposed through the generic graph query and AP242 dictionary/shape endpoints when the AP242 ontology is registered. |
| Registered ontology domains | Dynamic | Each registered ontology is advertised as `ontology:{id}` with a scoped query capability, taxonomy and generated resource shape. |
| OSLC Core/TRS | Read-only foundation | Catalog/provider discovery, bounded query, URL-encoded resource IDs, instance shapes and TRS base/change-log endpoints are available. |

The provider now emits both the existing flattened compatibility fields and
canonical `oslc:domain`/`services` capability structures. Shape properties retain
the legacy descriptor fields and additionally expose `uri` and
`propertyDefinition` for standard vocabulary terms.

## Resource and shape behavior

- Query resource types are allow-listed; ontology queries are scoped to the
  registered ontology ID and prefix.
- Resource payloads include a stable OSLC URI, `rdf:type`, service-provider URI,
  title, selected properties and outgoing relation links.
- AM/RM resource types receive profile-specific `rdf:type` and
  `oslc:instanceShape` values based on semantic labels and source metadata.
- Generated ontology shapes combine OWL semantic terms, SHACL constraints and
  dictionary fallback properties. `minCount`, `maxCount`, datatype, node kind,
  class, messages and descriptions are retained when available.
- Unknown shape IDs are rejected instead of causing arbitrary ontology
  inspection.

## Deliberate scope and remaining gaps

- OSLC CM and QM are now advertised as read-only discovery profiles. Their
  authoring services, creation factories and full domain-specific formats are
  still not implemented.
- The current server is read-only. Creation factories, update/delete methods and
  delegated UI dialogs are not exposed. Mutations must use the canonical
  publication boundary.
- Turtle/JSON-LD negotiation and full RDF/XML representations are not yet
  provided by the JSON facade. Add them before claiming conformance to a
  production OSLC domain server.
- Live provider validation still requires `OSLC_REMOTE_BASE_URL` (and optional
  `OSLC_REMOTE_TOKEN`) to be configured.

## Verification

The focused OSLC, GraphRAG and agent-control-plane suites pass together:

```text
30 passed
```
