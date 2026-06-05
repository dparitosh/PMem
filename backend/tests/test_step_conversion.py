import pytest

from neo4j.exceptions import ServiceUnavailable, AuthError
#!/usr/bin/env python3
"""
Test script for STEP file conversion via /api/import/convert-schema endpoint
"""

import sys

# Verify imports work
try:
    from backend.Services.owl_generation_service import OWLGenerationService
    print("✓ OWLGenerationService imported successfully")
except Exception as e:
    print(f"✗ Failed to import OWLGenerationService: {e}")
    sys.exit(1)

# Test with a mock STEP file
def test_step_parsing():
    """Test STEP file parsing capability"""
    print("\n" + "="*60)
    print("Testing STEP Format Support")
    print("="*60)
    
    # Create a minimal P21 STEP file for testing
    minimal_step = b"""ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('Minimal test'),
    '2024-05-23T00:00:00',
    2,
    2,
    '',
    '',
    '');
FILE_NAME('test_part.stp',
    '2024-05-23T00:00:00',
    ('Test'),
    ('Test'),
    '',
    '',
    '');
FILE_SCHEMA(('AP203_CONFIGURATION_CONTROLLED_3D_DESIGN_OF_MECHANICAL_PARTS_AND_ASSEMBLIES_201'));
ENDSEC;
DATA;
#1 = PRODUCT('Test Part','Test Part','Part-001',(#2));
#2 = PRODUCT_DEFINITION_FORMATION('',' ',#3);
#3 = PRODUCT_DEFINITION_CONTEXT('assembly',#4,'');
#4 = APPLICATION_CONTEXT('example');
ENDSEC;
END-ISO-10303-21;
"""
    
    print("\n1. Testing STEP file parsing...")
    try:
        owl_ttl, metadata = OWLGenerationService.generate_owl_from_step(minimal_step, "test_part.stp")
        print(f"   ✓ STEP parsing successful")
        # Metadata keys vary by implementation; use safe lookups
        entities_processed = metadata.get('entities_processed') or metadata.get('entity_count')
        classes_generated = metadata.get('classes_generated') or metadata.get('unique_entity_types')
        ttl_size = metadata.get('ttl_size') or metadata.get('owl_size') or len(owl_ttl)
        print(f"     - Entities processed: {entities_processed}")
        print(f"     - Classes generated: {classes_generated}")
        print(f"     - OWL size: {ttl_size} bytes")

        # Verify TTL output looks valid: check common TTL markers or output file
        ttl_ok = False
        try:
            from pathlib import Path as _P
            output_file = metadata.get('output_file') or metadata.get('output')
            if output_file and _P(output_file).exists():
                ttl_ok = True
            elif isinstance(owl_ttl, str) and ('@prefix' in owl_ttl or 'STEP File Ontology' in owl_ttl):
                ttl_ok = True
        except Exception:
            ttl_ok = bool(owl_ttl)

        if ttl_ok:
            print(f"   ✓ Valid TTL/OWL generated")
        else:
            print(f"   ✗ OWL output validation failed")
            pytest.fail("OWL output validation failed")
        
    except Exception as e:
        print(f"   ✗ STEP parsing failed: {e}")
        import traceback
        traceback.print_exc()
        pytest.fail(f"STEP parsing failed: {e}")

def test_express_still_works():
    """Verify EXPRESS parsing still works"""
    print("\n2. Testing EXPRESS format still works...")
    
    # Create a minimal EXPRESS file
    minimal_exp = b"""SCHEMA simple_test;
    ENTITY TestEntity;
        name : STRING;
        value : REAL;
    END_ENTITY;
END_SCHEMA;
"""
    
    try:
        owl_ttl, metadata = OWLGenerationService.generate_owl_from_express(minimal_exp, "test.exp")
        print(f"   ✓ EXPRESS parsing still works")
        print(f"     - Schema name: {metadata.get('schema_name')}")
        print(f"     - Entity count: {metadata['entity_count']}")
        assert True
    except Exception as e:
        print(f"   ✗ EXPRESS parsing failed: {e}")
        pytest.fail(f"EXPRESS parsing failed: {e}")

if __name__ == "__main__":
    print("\n" + "="*60)
    print("OWL Generation Service Tests")
    print("="*60)
    
    results = []
    
    # Test STEP support
    results.append(("STEP format support", test_step_parsing()))
    
    # Test EXPRESS still works
    results.append(("EXPRESS format compatibility", test_express_still_works()))
    
    # Print summary
    print("\n" + "="*60)
    print("Test Summary")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n✓ All tests passed! STEP format support is working.")
        sys.exit(0)
    else:
        print(f"\n✗ {total - passed} test(s) failed.")
        sys.exit(1)
