# Annotation and individual metrics review — 2026-10-28

The reported zero declaration counts are correct for the currently retained AP242 and PLMXML ontologies. They do not mean annotations or imported business records are absent.

| Retained ontology | Annotation statements in source | Verified published annotation statements | Explicit annotation-property declarations | Explicit named-individual declarations |
| --- | ---: | ---: | ---: | ---: |
| AP242 Domain Model (`domain_model_40c563f76dee4839`) | 51,731 | 51,731 | 0 | 0 |
| Teamcenter PLMXML (`plmxmlschema_a7251ea743764fec`) | 5,394 | 5,394 | 0 | 0 |

The AP242 projection contains 51,730 literal annotation statements and one resource-valued annotation; PLMXML contains 5,393 literal annotations and one resource-valued annotation. These counts match the retained RDF. Neither source contains language-tagged annotation values; a regression fixture independently checks preservation of language tags. Recognized annotations in this comparison comprise locally declared annotation predicates plus the explicitly checked RDFS, OWL and SKOS annotation predicates, not every arbitrary property.

The complete published projection contains **55,554 records explicitly typed with recognized DEPO business classes** and zero explicit `owl:NamedIndividual` declarations. Domain typing does not require that additional declaration. Counts are projection records, not deduplicated physical products: the same IRI in different ontology projections remains separate. Graph resources also include vocabulary and anonymous expression resources.

The separately embedded IDO/DEPO reference bundle contains **42 explicitly declared annotation properties** and zero named-individual declarations. This offline foundation is not itself a customer graph publication. Its declarations must not be silently added to the Home page's published-projection counts.

## Changes

- Home labels the metric **Declared annotation properties** and explains why annotation statements can exist when this count is zero.
- Home separately displays **Business instance records**, preserving the explicit **Declared named individuals** metric.
- The graph aggregate recognizes both retained `rdf_types` and explicit type relationships, counts a resource once per category, and computes business records within the existing aggregate without another graph scan/query.
- Detailed definitions use an expandable explanation. No assertions, ontology artifacts, approvals or publications were modified to inflate counts.
- The ontology scope control remains in normal scroll flow so it cannot overlay metric labels with a translucent sticky background.

## Validation

- Read-only retained RDF inventories compared with the actual published JSON literal properties and annotation relationships; both models matched.
- Actual revised graph aggregate returned 7,274 classes, zero annotation-property declarations, zero named-individual declarations and 55,554 recognized business-instance records.
- Eight backend inventory/projection/metrics tests passed; eight Home presentation and scope tests passed. Fixtures cover annotations without local property declarations, explicitly declared annotation properties, resource-valued annotations, language tags, and typed individuals with and without an explicit named-individual declaration.
- This is an asserted-data inventory review. It does not infer missing assertions, certify mappings or establish OWL-DL consistency.
