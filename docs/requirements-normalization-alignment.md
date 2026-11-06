# Requirements Normalization And Ontology Alignment

## Audit Summary

Current DEPO capabilities already cover PLMXML requirements, graph search, OSLC linked-data endpoints, Semantic Bridge, AP242/STEP parsing, MBSE/XMI readiness, and ReqIF 1.2 standalone parsing. The missing layer was a canonical requirement normalization model that can accept extracted rows from Word, Excel, HTML, ReqIF, or other unstructured pipelines before loading or linking.

## Canonical Requirement Model

A normalized requirement should keep:

- `id`: stable requirement identifier such as `REQ-006`
- `title`: short human-readable label
- `text`: requirement statement
- `status`, `owner`, `priority`, `verification_method`
- `source_name`, `source_type`
- relation targets such as part, function, process, PLM object, verification case, parent/refined requirement

## Ontology Alignment

| Canonical concept | ReqIF | OSLC RM | MBSE / SysML | AP242 | PLM |
| --- | --- | --- | --- | --- | --- |
| Requirement | `SPEC-OBJECT` | `oslc_rm:Requirement` | `sysml:Requirement` | Requirement constrains product/PMI context | Requirement / RequirementRevision |
| Requirement document | `SPECIFICATION` | Requirement collection | Package / requirement group | Product requirement set | Specification document |
| Requirement relation | `SPEC-RELATION` | linked resource relation | satisfy, derive, refine, verify | allocation to product/feature/PMI | trace link / relation object |
| Attribute | `ATTRIBUTE-DEFINITION-*` | property | value property / stereotype tag | product/manufacturing property | PLM attribute |
| Verification | relation or attribute | validation link | verify relationship | inspection/test context | test/inspection object |

## Graph Projection

Recommended Neo4j projection:

- Nodes: `Requirement`, `OSLCRequirement`, `ReqIFSpecObject`
- Cross-domain nodes: `Function`, `Block`, `Part`, `Product`, `PMIAnnotation`, `Process`, `Operation`, `Change`
- Relationships: `SATISFIES`, `VERIFIES`, `ALLOCATED_TO`, `RELATED_PART`, `RELATED_PROCESS`, `DERIVES`, `REFINES`
- Indexes: `Requirement.id`, `Requirement.source_name`, `Requirement.requirement_id`

## Release Recommendation

Use ReqIF 1.2 as the interchange backbone, OSLC RM as the linked-data API surface, MBSE/SysML as the systems engineering semantic layer, AP242 as the product/PMI engineering context, and PLM as the lifecycle/BOM/process/change execution layer.
