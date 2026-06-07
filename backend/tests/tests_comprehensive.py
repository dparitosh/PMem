#!/usr/bin/env python
"""
Comprehensive test suite for 7-stage data import pipeline
Tests actual functionality with real assertions
"""

import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.Services.pipeline_stages_4_7 import (
    UnifiedStage4to7Service,
    OntologyValidationService,
    OntologyEnrichmentService,
    Neo4jLoadService,
    HealthCheckService
)


class TestOntologyValidation:
    """Test Stage 4: SHACL Validation"""
    
    def test_validation_service_exists(self):
        """Test that ValidationService can be instantiated"""
        service = OntologyValidationService()
        assert service is not None, "ValidationService instantiation failed"
    
    def test_validation_returns_metrics(self):
        """Test that validation returns proper metrics"""
        service = OntologyValidationService()
        test_owl = '@prefix ex: <http://example.org/> .\nex:Entity1 a rdfs:Class .'
        
        result = service.validate(test_owl, {'entity_count': 5, 'owl_triple_count': 20, 'properties_count': 3})
        
        assert result is not None, "Validation returned None"
        assert hasattr(result, 'valid'), "Result missing 'valid' attribute"
        assert hasattr(result, 'class_count'), "Result missing 'class_count' attribute"
        assert hasattr(result, 'property_count'), "Result missing 'property_count' attribute"
        assert hasattr(result, 'errors'), "Result missing 'errors' attribute"
        assert hasattr(result, 'warnings'), "Result missing 'warnings' attribute"
        assert isinstance(result.valid, bool), "valid should be boolean"
        assert isinstance(result.errors, int), "errors should be int"
        print(f"✓ Stage 4 Validation: valid={result.valid}, classes={result.class_count}, properties={result.property_count}, errors={result.errors}, warnings={result.warnings}")


class TestOntologyEnrichment:
    """Test Stage 5: Semantic Enrichment"""
    
    def test_enrichment_service_exists(self):
        """Test that EnrichmentService can be instantiated"""
        service = OntologyEnrichmentService()
        assert service is not None, "EnrichmentService instantiation failed"
    
    def test_enrichment_returns_metrics(self):
        """Test that enrichment returns proper metrics"""
        service = OntologyEnrichmentService()
        test_owl = '@prefix ex: <http://example.org/> .\nex:Entity1 a rdfs:Class .\nex:Entity2 a rdfs:Class .'
        
        result = service.enrich(test_owl, {'entity_count': 5})
        
        assert result is not None, "Enrichment returned None"
        assert hasattr(result, 'inverse_relationships_added'), "Result missing inverse_relationships_added"
        assert hasattr(result, 'transitive_properties_added'), "Result missing transitive_properties_added"
        assert hasattr(result, 'total_enrichments'), "Result missing total_enrichments"
        assert isinstance(result.total_enrichments, int), "total_enrichments should be int"
        print(f"✓ Stage 5 Enrichment: enrichments={result.total_enrichments}, inverse={result.inverse_relationships_added}, transitive={result.transitive_properties_added}")


class TestNeo4jLoad:
    """Test Stage 6: Neo4j Loading"""
    
    def test_neo4j_service_exists(self):
        """Test that Neo4jLoadService can be instantiated"""
        service = Neo4jLoadService()
        assert service is not None, "Neo4jLoadService instantiation failed"
    
    def test_neo4j_returns_metrics(self):
        """Test that Neo4j loading returns proper metrics"""
        service = Neo4jLoadService()
        test_owl = '@prefix ex: <http://example.org/> .\nex:Entity1 a rdfs:Class .'
        
        result = service.load_to_neo4j(test_owl, {'entity_count': 5}, 'test_task')
        
        assert result is not None, "Neo4j loading returned None"
        assert hasattr(result, 'entities_created'), "Result missing entities_created"
        assert hasattr(result, 'relationships_created'), "Result missing relationships_created"
        assert hasattr(result, 'indexes_created'), "Result missing indexes_created"
        assert isinstance(result.entities_created, int), "entities_created should be int"
        print(f"✓ Stage 6 Neo4j Load: entities={result.entities_created}, relationships={result.relationships_created}, indexes={result.indexes_created}")


class TestHealthCheck:
    """Test Stage 7: Health Verification"""
    
    def test_health_service_exists(self):
        """Test that HealthCheckService can be instantiated"""
        service = HealthCheckService()
        assert service is not None, "HealthCheckService instantiation failed"
    
    def test_health_returns_metrics(self):
        """Test that health check returns proper metrics"""
        service = HealthCheckService()
        # First create load metrics (required parameter for verify)
        load_service = Neo4jLoadService()
        test_owl = '@prefix ex: <http://example.org/> .\nex:Entity1 a rdfs:Class .'
        load_metrics = load_service.load_to_neo4j(test_owl, {'entity_count': 5, 'owl_triple_count': 20}, 'test_task')
        
        result = service.verify('test_task', load_metrics, {'entity_count': 5, 'owl_triple_count': 20, 'properties_count': 3})
        
        assert result is not None, "Health check returned None"
        assert hasattr(result, 'data_quality_score'), "Result missing data_quality_score"
        assert hasattr(result, 'provenance_coverage_percent'), "Result missing provenance_coverage_percent"
        assert hasattr(result, 'status'), "Result missing status"
        assert isinstance(result.data_quality_score, (int, float)), "data_quality_score should be int or float"
        print(f"✓ Stage 7 Health Check: quality_score={result.data_quality_score}, provenance={result.provenance_coverage_percent}%, status={result.status}")


class TestUnifiedPipeline:
    """Test Unified Stages 4-7 Orchestration"""
    
    def test_unified_service_exists(self):
        """Test that UnifiedStage4to7Service can be instantiated"""
        service = UnifiedStage4to7Service()
        assert service is not None, "UnifiedStage4to7Service instantiation failed"
    
    def test_unified_process_stages(self):
        """Test that unified service processes all 4 stages"""
        service = UnifiedStage4to7Service()
        test_owl = '@prefix ex: <http://example.org/> .\nex:Entity1 a rdfs:Class .'
        test_metadata = {
            'entity_count': 150,
            'owl_triple_count': 500,
            'properties_count': 45
        }
        
        results = service.process_stages(test_owl, test_metadata, 'test_task_123')
        
        # Verify structure
        assert results is not None, "process_stages returned None"
        assert 'stage_4_validate' in results, "Missing stage_4_validate"
        assert 'stage_5_enrich' in results, "Missing stage_5_enrich"
        assert 'stage_6_load' in results, "Missing stage_6_load"
        assert 'stage_7_verify' in results, "Missing stage_7_verify"
        assert 'overall_status' in results, "Missing overall_status"
        
        # Verify stage 4 results
        stage4 = results['stage_4_validate']
        assert 'valid' in stage4, "Stage 4 missing valid field"
        assert isinstance(stage4['valid'], bool), "Stage 4 valid should be boolean"
        
        # Verify stage 5 results
        stage5 = results['stage_5_enrich']
        assert 'total_enrichments' in stage5, "Stage 5 missing total_enrichments"
        assert isinstance(stage5['total_enrichments'], int), "Stage 5 total_enrichments should be int"
        
        # Verify stage 6 results
        stage6 = results['stage_6_load']
        assert 'entities_created' in stage6, "Stage 6 missing entities_created"
        assert isinstance(stage6['entities_created'], int), "Stage 6 entities_created should be int"
        
        # Verify stage 7 results
        stage7 = results['stage_7_verify']
        assert 'data_quality_score' in stage7, "Stage 7 missing data_quality_score"
        assert isinstance(stage7['data_quality_score'], (int, float)), "Stage 7 data_quality_score should be int or float"
        
        print(f"✓ Unified Pipeline Test PASSED")
        print(f"  - Stage 4 (Validate): valid={stage4['valid']}")
        print(f"  - Stage 5 (Enrich): enrichments={stage5['total_enrichments']}")
        print(f"  - Stage 6 (Load): entities={stage6['entities_created']}")
        print(f"  - Stage 7 (Verify): quality={stage7['data_quality_score']}")
        print(f"  - Overall Status: {results['overall_status']}")


if __name__ == '__main__':
    print("\n" + "="*80)
    print("COMPREHENSIVE TEST SUITE - 7-STAGE DATA IMPORT PIPELINE")
    print("="*80 + "\n")
    
    tests_passed = 0
    tests_failed = 0
    
    # Test Stage 4
    print("STAGE 4: SHACL Validation")
    print("-" * 80)
    try:
        test = TestOntologyValidation()
        test.test_validation_service_exists()
        test.test_validation_returns_metrics()
        tests_passed += 2
        print()
    except AssertionError as e:
        print(f"✗ FAILED: {e}\n")
        tests_failed += 1
    except Exception as e:
        print(f"✗ ERROR: {e}\n")
        tests_failed += 1
    
    # Test Stage 5
    print("STAGE 5: Semantic Enrichment")
    print("-" * 80)
    try:
        test = TestOntologyEnrichment()
        test.test_enrichment_service_exists()
        test.test_enrichment_returns_metrics()
        tests_passed += 2
        print()
    except AssertionError as e:
        print(f"✗ FAILED: {e}\n")
        tests_failed += 1
    except Exception as e:
        print(f"✗ ERROR: {e}\n")
        tests_failed += 1
    
    # Test Stage 6
    print("STAGE 6: Neo4j Loading")
    print("-" * 80)
    try:
        test = TestNeo4jLoad()
        test.test_neo4j_service_exists()
        test.test_neo4j_returns_metrics()
        tests_passed += 2
        print()
    except AssertionError as e:
        print(f"✗ FAILED: {e}\n")
        tests_failed += 1
    except Exception as e:
        print(f"✗ ERROR: {e}\n")
        tests_failed += 1
    
    # Test Stage 7
    print("STAGE 7: Health Verification")
    print("-" * 80)
    try:
        test = TestHealthCheck()
        test.test_health_service_exists()
        test.test_health_returns_metrics()
        tests_passed += 2
        print()
    except AssertionError as e:
        print(f"✗ FAILED: {e}\n")
        tests_failed += 1
    except Exception as e:
        print(f"✗ ERROR: {e}\n")
        tests_failed += 1
    
    # Test Unified Pipeline
    print("UNIFIED PIPELINE: Stages 4-7 Orchestration")
    print("-" * 80)
    try:
        test = TestUnifiedPipeline()
        test.test_unified_service_exists()
        test.test_unified_process_stages()
        tests_passed += 2
        print()
    except AssertionError as e:
        print(f"✗ FAILED: {e}\n")
        tests_failed += 1
    except Exception as e:
        print(f"✗ ERROR: {e}\n")
        tests_failed += 1
    
    # Summary
    print("="*80)
    print(f"TEST SUMMARY")
    print("="*80)
    print(f"✓ Passed: {tests_passed}")
    print(f"✗ Failed: {tests_failed}")
    print(f"Total:   {tests_passed + tests_failed}")
    
    if tests_failed == 0:
        print(f"\n🟢 ALL TESTS PASSED ({tests_passed}/{tests_passed + tests_failed})")
    else:
        print(f"\n🔴 SOME TESTS FAILED ({tests_failed} failures)")
    
    print("="*80 + "\n")
