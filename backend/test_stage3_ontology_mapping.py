#!/usr/bin/env python3
"""
Test script for Stage 3: Ontology Mapping Service
Tests entity similarity detection, namespace mapping, and constraint merging
"""

from backend.services.ontology_mapping_service import (
    OntologyMappingService,
    TargetOntologyRegistry,
    EntityMapping,
    map_express_to_ontology,
)


def test_string_similarity():
    """Test string similarity matching"""
    print("\n" + "="*70)
    print("TEST 1: String Similarity Detection")
    print("="*70)
    
    test_cases = [
        ("product_definition", "product_definition", 1.0, "exact match"),
        ("product_definition", "Product", 0.85, "substring"),
        ("part_design", "part_definition", 0.6, "similar names"),
        ("assembly_item", "assembly", 0.85, "substring"),
        ("representation_item", "representation", 0.85, "substring"),
    ]
    
    for s1, s2, expected_min, desc in test_cases:
        score = OntologyMappingService.string_similarity(s1, s2)
        status = "✓" if score >= expected_min else "✗"
        print(f"{status} {desc:20} | '{s1}' vs '{s2}' = {score:.2f} (expected >= {expected_min})")


def test_entity_similarity():
    """Test entity similarity detection"""
    print("\n" + "="*70)
    print("TEST 2: Entity Similarity Detection")
    print("="*70)
    
    source_entities = [
        "product_definition",
        "product_structure", 
        "geometric_representation_context",
        "cartesian_point",
        "direction",
        "axis2_placement_3d"
    ]
    
    target_ontology = TargetOntologyRegistry.get_ontology('ap242_product')
    target_entities = target_ontology['entities']
    
    print(f"\nSource entities: {len(source_entities)}")
    print(f"Target entities: {len(target_entities)}")
    
    similarities = OntologyMappingService.find_similar_entities(
        source_entities,
        target_entities,
        threshold=0.6
    )
    
    print(f"\nMatches found (threshold=0.6): {len(similarities)}")
    for source, target, confidence in similarities:
        print(f"  {source:30} → {target:30} [{confidence:.2%}]")
    
    if len(similarities) < len(source_entities):
        unmapped = [e for e in source_entities if not any(s[0] == e for s in similarities)]
        print(f"\nUnmapped entities: {unmapped}")


def test_normalize_name():
    """Test entity name normalization"""
    print("\n" + "="*70)
    print("TEST 3: Entity Name Normalization")
    print("="*70)
    
    test_cases = [
        "product_definition",
        "source_product_definition",
        "product_definition_type",
        "PRODUCT_DEFINITION",
        "impl_product",
        "abstract_representation",
    ]
    
    for name in test_cases:
        normalized = OntologyMappingService.normalize_name(name)
        print(f"  {name:30} → {normalized}")


def test_target_ontologies():
    """Test available target ontologies"""
    print("\n" + "="*70)
    print("TEST 4: Available Target Ontologies")
    print("="*70)
    
    ontologies = TargetOntologyRegistry.list_ontologies()
    print(f"\nAvailable ontologies: {ontologies}")
    
    for onto_name in ontologies:
        onto = TargetOntologyRegistry.get_ontology(onto_name)
        print(f"\n  {onto_name}:")
        print(f"    Namespace: {onto['namespace']}")
        print(f"    Entities: {len(onto['entities'])}")
        print(f"    Sample: {onto['entities'][:3]}")


def test_mapping_report():
    """Test mapping report generation"""
    print("\n" + "="*70)
    print("TEST 5: Mapping Report Generation")
    print("="*70)
    
    # Create sample mappings
    mappings = [
        EntityMapping(
            source_entity="product_definition",
            target_entity="Product",
            confidence=0.95,
            reason="Very similar name",
            property_mappings={"id": "id", "name": "name"}
        ),
        EntityMapping(
            source_entity="representation_item",
            target_entity="Representation",
            confidence=0.85,
            reason="Similar name with related properties",
            property_mappings={"type": "type"}
        ),
    ]
    
    unmapped = ["geometric_context", "coordinate_system"]
    
    report = OntologyMappingService.generate_mapping_report(mappings, unmapped)
    
    print(f"\nMapping Statistics:")
    print(f"  Total entities: {report['total_entities']}")
    print(f"  Mapped: {report['mapped_entities']}")
    print(f"  Unmapped: {report['unmapped_entities']}")
    print(f"  Coverage: {report['coverage']:.1%}")
    print(f"  Average confidence: {report['average_confidence']:.2%}")
    print(f"  High confidence (>= 0.9): {report['high_confidence_mappings']}")
    print(f"  Medium confidence (0.7-0.9): {report['medium_confidence_mappings']}")
    print(f"  Low confidence (< 0.7): {report['low_confidence_mappings']}")
    
    print(f"\nTop mappings:")
    for m in report['mappings'][:3]:
        print(f"  {m['source']:30} → {m['target']:30} [{m['confidence']:.2%}] - {m['reason']}")


def test_owl_alignment():
    """Test OWL namespace alignment"""
    print("\n" + "="*70)
    print("TEST 6: OWL Namespace Alignment")
    print("="*70)
    
    # Sample OWL
    source_owl = """
@prefix ex: <http://express.schema/product#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .

ex:product_definition a owl:Class ;
    rdfs:label "Product Definition" .

ex:product_definition_id a owl:DatatypeProperty ;
    rdfs:domain ex:product_definition ;
    rdfs:range xsd:string .
"""
    
    source_namespace = "http://express.schema/product#"
    target_namespace = "http://iso.org/iso10303/ap242/product#"
    
    mappings = [
        EntityMapping(
            source_entity="product_definition",
            target_entity="product_definition",
            confidence=1.0,
            reason="Exact match",
            property_mappings={"id": "id"}
        )
    ]
    
    aligned_owl = OntologyMappingService.align_owl_namespaces(
        source_owl,
        source_namespace,
        target_namespace,
        mappings
    )
    
    print(f"\nOriginal namespace: {source_namespace}")
    print(f"Target namespace: {target_namespace}")
    print(f"\nNamespace alignment applied:")
    
    if target_namespace in aligned_owl:
        print(f"  ✓ Namespace prefix updated")
    
    if "owl:equivalentClass" in aligned_owl:
        print(f"  ✓ owl:equivalentClass mappings added")
    
    print(f"\nSample of aligned OWL (first 300 chars):")
    print(aligned_owl[:300] + "...")


def run_all_tests():
    """Run all tests"""
    print("\n")
    print("█" * 70)
    print("  Stage 3: Ontology Mapping Service - Comprehensive Test Suite")
    print("█" * 70)
    
    try:
        test_string_similarity()
        test_entity_similarity()
        test_normalize_name()
        test_target_ontologies()
        test_mapping_report()
        test_owl_alignment()
        
        print("\n" + "█" * 70)
        print("  ✓ ALL TESTS COMPLETED SUCCESSFULLY")
        print("█" * 70 + "\n")
        
    except Exception as e:
        print(f"\n✗ TEST FAILED: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    run_all_tests()

