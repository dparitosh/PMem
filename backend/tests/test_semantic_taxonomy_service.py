from backend.Services.semantic_taxonomy_service import (
    SemanticTaxonomyService,
    SkosNeo4jRepository,
    normalize_skos_payload,
)


def _payload():
    return {
        "scheme": {"scheme_id": "depo-taxonomy", "pref_label": "DEPO Taxonomy", "version": "1"},
        "concepts": [
            {
                "concept_id": "asset",
                "pref_label": "Asset",
                "alt_labels": ["Equipment"],
                "definition": "A managed business object.",
                "narrower": ["bearing"],
            },
            {
                "concept_id": "bearing",
                "pref_label": "Bearing",
                "alt_labels": ["SKF bearing"],
                "definition": "Rotating component used in motor assemblies.",
                "broader": ["asset"],
                "related": ["failure-mode"],
                "mappings": {"exactMatch": ["ap242:Part"]},
            },
            {
                "concept_id": "failure-mode",
                "pref_label": "Failure Mode",
                "alt_labels": ["Risk"],
            },
        ],
    }


def test_skos_search_uses_synonyms_hierarchy_and_mappings():
    _, concepts = normalize_skos_payload(_payload())

    synonym_results = SemanticTaxonomyService.search(concepts, "SKF", 10)
    assert synonym_results[0]["concept_id"] == "bearing"
    assert "synonym contains query" in synonym_results[0]["reasons"]

    mapping_results = SemanticTaxonomyService.search(concepts, "ap242", 10)
    assert mapping_results[0]["concept_id"] == "bearing"
    assert "mapping target match" in mapping_results[0]["reasons"]


def test_skos_traversal_returns_connected_taxonomy_slice():
    _, concepts = normalize_skos_payload(_payload())

    result = SemanticTaxonomyService.traverse(concepts, "asset", "narrower", 2)

    assert {node["concept_id"] for node in result["nodes"]} == {"asset", "bearing"}
    assert result["edges"] == [{"source": "asset", "target": "bearing", "type": "skos:narrower"}]


def test_skos_validation_detects_duplicate_labels_and_cycles():
    payload = _payload()
    payload["concepts"].append({"concept_id": "equipment-duplicate", "pref_label": "Equipment"})
    payload["concepts"][0]["broader"] = ["bearing"]
    _, concepts = normalize_skos_payload(payload)

    validation = SemanticTaxonomyService.validate(concepts)

    assert validation["valid"] is False
    assert any(issue["code"] == "duplicate_label" for issue in validation["issues"])
    assert any(issue["code"] == "taxonomy_cycle" for issue in validation["issues"])


def test_skos_neo4j_storage_plan_is_parameterized_and_separates_skos_labels():
    scheme, concepts = normalize_skos_payload(_payload())

    plan = SkosNeo4jRepository.storage_plan(scheme, concepts)
    all_cypher = "\n".join(step["cypher"] for step in plan)

    assert "SkosConcept" in all_cypher
    assert "OntologyClass" not in all_cypher
    assert "MERGE (c:SkosConcept {schemeId: row.schemeId, conceptId: row.conceptId})" in all_cypher
    assert "REQUIRE (c.schemeId, c.conceptId) IS UNIQUE" in all_cypher
    assert any(
        step["name"] == "drop_legacy_skos_concept_constraint"
        and step["cypher"] == "DROP CONSTRAINT skos_concept_id IF EXISTS"
        for step in plan
    )
    assert any(step["name"] == "remove_stale_concepts" for step in plan)
    assert any(step["name"] == "remove_stale_relationships" for step in plan)
    assert "Bearing" not in all_cypher
    assert any(step["name"] == "upsert_hierarchy" and step["params"]["rows"] for step in plan)
