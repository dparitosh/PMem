# OData and OpenAPI review — 2026-10-01

> Dated audit record: use [the current audit index](README.md) for latest validation and acceptance status. Findings and test counts below belong to their recorded review; they are not a current release certificate.

Reviewed shared contract generation, all ten service entry points and capability
lists, authorization helpers, agent catalog validation, deployment checks and
existing contract tests. OData currently exposes operation discovery only;
it does not expose PostgreSQL rows, ontology terms, jobs or products as business
entity sets.

## Remediation

C01–C06 are corrected in the shared contract factory and OData router. C07 now
documents recognized read, write, metadata-registry and administrator guards.
C09 adds coverage for all ten capability declarations, paging, errors, key lookup
and an independently validated typed OpenAPI document. Deployment diagnostics
check operation IDs, incompatible null types and duplicate OData keys.

C10 reports unavailable services separately, continues with other services and
checks document compatibility. Complete tool input/output and authorization
comparison remains open. C08 remains open: converting generic business payloads
requires endpoint-specific DTOs and compatibility tests. Customer infrastructure
and every service's full generated schema have not been validated here.

## Findings

| ID | Priority | Code | Defect and consequence | Required correction |
| --- | --- | --- | --- | --- |
| C01 | P1 | backend/depo_platform/service_runtime.py:93; backend/qif/models.py:36 | Factory changes the document label to 3.0.3 without converting Pydantic JSON Schema. Reproduction with release-pinned FastAPI 0.141.1/Pydantic 2.13.5 emits anyOf containing type:null for QifTaskResponse.validation. Null type is invalid in OAS 3.0.3. Gateway import/client generation can reject or misinterpret it. | Generate genuinely compatible 3.0 schemas, or deliberately adopt 3.1 and update gateway/deployment consumers. Validate the complete document, not its version string. |
| C02 | P2 | backend/depo_platform/odata.py:69; backend/data_pipeline_service/app.py:29 | Id is method:path, but five pipeline capabilities advertise the same POST jobs/definitions/{job_id}/{version}/run operation. All five have the same declared entity key. Clients can merge or overwrite entities. | Use stable unique capability IDs, distinguish job profiles with an explicit profile field, or deduplicate operations. Reject duplicate keys at startup. |
| C03 | P2 | backend/depo_platform/odata.py:92 | Unsupported $filter/$orderby/$select and other system query options are silently ignored. Reproduction filtering Name=Alpha returns both Alpha and Beta with HTTP 200. | Implement supported options or explicitly reject unsupported system options with an OData error. Advertise capabilities/limitations. |
| C04 | P2 | backend/depo_platform/odata.py:95 | $top uses ge=1. Valid $top=0 requests fail with HTTP 422 instead of an empty result. | Accept zero; test zero, skip beyond collection, count and invalid values. |
| C05 | P2 | backend/depo_platform/odata.py:82–107 | No OData-Version response header; invalid paging returns FastAPI detail envelopes rather than OData error objects. Reproduced with the shared router. | Add OData-Version:4.0 and scope protocol-compatible error handling to the OData routes. |
| C06 | P2 gap | backend/depo_platform/odata.py:92 | Metadata declares keyed ServiceCapability entities, but no entity-by-key read route exists. Reproduction of ServiceCapabilities('GET:%2Fa') returns 404. General OData clients cannot navigate the advertised key. | Supply key lookup with correct string-key escaping, or explicitly document the limited discovery surface and assess target-client requirements. |
| C07 | P2 | backend/depo_platform/authorization.py:14,45; service router dependencies | Authorization is read directly from Request headers, without OpenAPI security schemes/operation requirements. Runtime protection exists, but generated docs/client contracts do not describe required bearer/API keys or separate approval credentials. | Add documentation-only/validated security dependencies and service-specific authorization descriptions without weakening existing checks. Test protected versus public operations. |
| C08 | P2 gap | backend/agentic_service/router.py; backend/ontology_service/router.py; backend/data_pipeline_service/router.py | Many endpoints accept and return generic dicts, so OpenAPI cannot specify required business fields, approval requirements, nested outputs or discriminated job/tool schemas. Generated clients have incomplete contracts. | Add typed request/response DTOs incrementally, preserving runtime validation and backward compatibility; define error/status/media-type responses. |
| C09 | P2 | infra/deployment/test-depo-deployment.ps1:108; backend/tests/test_service_contracts.py:7; backend/tests/test_odata_catalog.py:9 | Release check tests OpenAPI version only. OData test named every_standalone_service exercises just four services, and only a happy-path collection/metadata request. It misses C01–C06 and key duplication. | Validate complete schemas, unique IDs/operation IDs, all ten service contracts, authentication metadata, paging/error cases and discovery route drift. |
| C10 | P2 gap | backend/agentic_service/router.py:456 | Live catalog validation only checks whether tool method/path exists. It does not validate input/response schemas, authorization, operation IDs or OData capability rows, and aborts on the first failed service. | Return per-service evidence and validate the complete catalog against schemas and credential contracts; retain unavailable-service results separately. |

## Inventory

Every listed service installs the shared OData router and shared OpenAPI factory.
Thus C01 and C03–C06 affect their shared infrastructure; C01 becomes observable
when the service publishes nullable/other incompatible JSON Schema constructs.
C07/C08 vary by route, and should not be interpreted as an authentication bypass.

| Service / port | Advertised capability rows | Duplicate Id values found |
| --- | ---: | --- |
| Schema Sets / QIF — 8010 | 4 | None |
| Ontology — 8011 | 16 | None |
| Agentic — 8012 | 11 | None |
| Graph — 8013 | 15 | None |
| Ingestion — 8014 | 15 | None |
| OSLC — 8015 | 5 | None |
| Catalog — 8016 | 4 | None |
| Data Products — 8017 | 6 | None |
| CEIM — 8018 | 14 | None |
| Data Pipeline — 8019 | 16 | One key repeated five times |

The 106 advertised rows are curated subsets, not complete endpoint inventories.
AST comparison checked capability declarations against directly included routers.
Graph traversal uses {iri:path} internally, which FastAPI normalizes in OpenAPI;
that spelling difference was not reported as route drift. Ingestion compatibility
imports require runtime resolution; static unmatched import paths are not treated
as confirmed missing endpoints.

## Reproductions and limits

Using the actual shared router/factory in FastAPI TestClient:

- $filter=Name eq 'Alpha': HTTP 200, two rows returned from a two-row fixture.
- $top=0: HTTP 422.
- Entity-key read: HTTP 404.
- OData-Version header absent.
- Typed QIF response under openapi=3.0.3: validation.anyOf includes type:null.
- AST inventory: five duplicate pipeline method/path keys.

Temporary test dependencies used the pinned FastAPI/Pydantic versions, but not
the entire production lock. No live PostgreSQL, Neo4j, gateway or all-service
process launch was attempted. Temporary dependencies were removed afterward.

## Primary specifications

- [OpenAPI 3.0.3 schema types and nullable](https://spec.openapis.org/oas/v3.0.3)
- [OData 4.0 URL conventions: unsupported system options and paging](https://docs.oasis-open.org/odata/odata/v4.0/os/part2-url-conventions/odata-v4.0-os-part2-url-conventions.html)

Fix C01 before relying on customer OpenAPI imports; address C02–C05 before
advertising this as a general OData v4-compatible catalog. Complete live gateway
import, client-generation and authentication acceptance afterward.
