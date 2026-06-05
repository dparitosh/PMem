#!/usr/bin/env python
"""Quick test of Stages 4-7 service"""

from backend.services.pipeline_stages_4_7 import UnifiedStage4to7Service

# Test Stage 4-7 service with sample data
service = UnifiedStage4to7Service()

test_metadata = {
    'entity_count': 150,
    'owl_triple_count': 500,
    'properties_count': 45
}

test_owl = '@prefix ex: <http://example.org/> .\nex:Entity1 a rdfs:Class .'

results = service.process_stages(
    test_owl,
    test_metadata,
    'test_task_123'
)

print('✓ Stages 4-7 service executed successfully')
print(f'  - Stage 4 Validate: {results["stage_4_validate"]["valid"]}')
print(f'  - Stage 5 Enrich: {results["stage_5_enrich"]["total_enrichments"]} enrichments')
print(f'  - Stage 6 Load: {results["stage_6_load"]["entities_created"]} entities')
print(f'  - Stage 7 Verify: {results["stage_7_verify"]["status"]}')
print(f'  - Overall: {results["overall_status"]}')

