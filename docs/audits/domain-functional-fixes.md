# Domain correctness fixes

> Dated audit record: use [the current audit index](README.md) for latest validation and acceptance status. Findings and test counts below belong to their recorded review; they are not a current release certificate.

Corrected per-entity provenance binding before Bill-of-Characteristics typing; added approved semantic release selection, source-system entry and separate execution/governance/publication credentials in Data Flow; retained qualified XML structure, text/tails and leaf attributes while preserving legacy leaf text mappings; introduced source-scoped CEIM IDs at canonical publication with remapped relationship endpoints and scope-aware entity resolution.

Production scoped publication requires source_system and completed tenant/project configuration. Existing graph IDs are not migrated automatically. Explicit legacy mode remains available for controlled compatibility; it does not resolve cross-source identity collisions. Publication inputs with an existing, different identity scope are rejected.

Three focused domain regression tests passed: mixed-standard engineering types in both input orders, repeated qualified XML/units with legacy text access, and distinct/idempotent scope identities with matching edge endpoints. Actual RDF/HTTP and frontend production-build verification remain pending because dependencies are absent. The broader mapping-pack and dimensional warehouse gaps require additional implementation and are not claimed complete. This update implements the corrections; live release acceptance checks remain pending.
