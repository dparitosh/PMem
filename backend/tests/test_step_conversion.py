import pytest

from neo4j.exceptions import ServiceUnavailable, AuthError
#!/usr/bin/env python3
"""
Test script for STEP file conversion via /api/import/convert-schema endpoint
"""

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

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

        assert metadata.get("owlready2", {}).get("engine") == "owlready2"
        assert "summary" in metadata.get("owlready2", {})
        
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
        assert metadata.get("owlready2", {}).get("engine") == "owlready2"
        assert True
    except Exception as e:
        print(f"   ✗ EXPRESS parsing failed: {e}")
        pytest.fail(f"EXPRESS parsing failed: {e}")


def test_ap242_ed5_stpx_metadata_detection():
    """STPX/AP242 XML should report the current ISO/TS 10303-4442 ed-5 namespace."""
    from backend.Services.ap242_domain_model import (
        AP242_DOMAIN_MODEL_NAMESPACE,
        AP242_DOMAIN_MODEL_SCHEMA_TOKEN,
        AP242_DOMAIN_MODEL_XSD_URL,
    )
    from backend.Services.step_parser import parse_step_metadata

    stpx = f"""<?xml version="1.0" encoding="UTF-8"?>
<Uos xmlns="{AP242_DOMAIN_MODEL_NAMESPACE}"
     xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
     xsi:schemaLocation="{AP242_DOMAIN_MODEL_NAMESPACE} {AP242_DOMAIN_MODEL_XSD_URL}">
  <Header><Name>AP242 ed5 smoke</Name></Header>
</Uos>
"""

    with tempfile.NamedTemporaryFile("w", suffix=".stpx", delete=False, encoding="utf-8") as tmp:
        tmp.write(stpx)
        path = Path(tmp.name)
    try:
        metadata = parse_step_metadata(path)
    finally:
        path.unlink(missing_ok=True)

    assert metadata.format == "stpx"
    assert metadata.namespace == AP242_DOMAIN_MODEL_NAMESPACE
    assert AP242_DOMAIN_MODEL_XSD_URL in metadata.schema_location
    assert metadata.file_schema == AP242_DOMAIN_MODEL_SCHEMA_TOKEN


def test_step_parser_extracts_shape_geometry_dimension_and_pmi():
    """Parser should populate semantic buckets, not only raw STEP rows."""
    from backend.Services.step_parser import parse_step_with_pmi

    step = """ISO-10303-21;
HEADER;
FILE_SCHEMA(('AP242_MANAGED_MODEL_BASED_3D_ENGINEERING'));
ENDSEC;
DATA;
#1 = PRODUCT('P-100','Pump Housing','Demo housing',());
#2 = SHAPE_REPRESENTATION('Body shape',(#5),#9);
#3 = ADVANCED_FACE('',(),#6,.T.);
#4 = CARTESIAN_POINT('origin',(0.0,0.0,0.0));
#5 = GEOMETRIC_TOLERANCE('GT1','Position tolerance','controls hole',#3,#4);
#6 = DIMENSIONAL_SIZE('D1','Hole diameter','nominal',25.0,#3);
#7 = DATUM_FEATURE('A','Primary datum','mounting face',#3);
#8 = ANNOTATION_TEXT_OCCURRENCE('NOTE1','Machined surface','Ra 1.6',#3);
#9 = GEOMETRIC_REPRESENTATION_CONTEXT(3);
ENDSEC;
END-ISO-10303-21;
"""

    with tempfile.NamedTemporaryFile("w", suffix=".stp", delete=False, encoding="utf-8") as tmp:
        tmp.write(step)
        path = Path(tmp.name)
    try:
        doc = parse_step_with_pmi(path)
    finally:
        path.unlink(missing_ok=True)

    assert doc.metadata.file_schema == "AP242_MANAGED_MODEL_BASED_3D_ENGINEERING"
    assert len(doc.cad_products) == 1
    assert len(doc.cad_representations) >= 2
    assert len(doc.cad_topology) == 1
    assert len(doc.cad_geometry) >= 1
    assert len(doc.geometric_tolerances) == 1
    assert len(doc.dimensions) == 1
    assert len(doc.datums) == 1
    assert len(doc.annotations) == 1
    assert doc.geometric_tolerances[0].toleranced_feature_refs


def test_step_parser_attaches_plus_minus_tolerance_to_dimension(tmp_path):
    """AP242 plus/minus tolerances are dimensional bounds, not geometric tolerances."""
    from backend.Services.step_parser import parse_step_with_pmi

    step = """ISO-10303-21;
HEADER;
FILE_SCHEMA(('AP242_MANAGED_MODEL_BASED_3D_ENGINEERING'));
ENDSEC;
DATA;
#1 = PRODUCT('P-100','Pump Housing','Demo housing',());
#2 = SHAPE_ASPECT('hole diameter','',#1,.T.);
#3 = DIMENSIONAL_SIZE(#2,'diameter');
#4 = LENGTH_MEASURE_WITH_UNIT(LENGTH_MEASURE(-0.2),#9);
#5 = LENGTH_MEASURE_WITH_UNIT(LENGTH_MEASURE(0.05),#9);
#6 = TOLERANCE_VALUE(#4,#5);
#7 = PLUS_MINUS_TOLERANCE(#6,#3);
#8 = SHAPE_DIMENSION_REPRESENTATION('',(#10),#11);
#9 = SI_UNIT(.MILLI.,.METRE.);
#10 = LENGTH_MEASURE_WITH_UNIT(LENGTH_MEASURE(35.0),#9);
#11 = GEOMETRIC_REPRESENTATION_CONTEXT(3);
ENDSEC;
END-ISO-10303-21;
"""

    step_path = tmp_path / "plus_minus_dimension.stp"
    step_path.write_text(step, encoding="utf-8")

    doc = parse_step_with_pmi(step_path)
    dimensional_size = next(dim for dim in doc.dimensions if dim.dimension_type == "DIMENSIONAL_SIZE")

    assert len(doc.geometric_tolerances) == 0
    assert dimensional_size.lower_tolerance == -0.2
    assert dimensional_size.upper_tolerance == 0.05


def test_step_parser_does_not_count_product_definition_rows_as_products(tmp_path):
    """Product/version/view STEP rows should not all inflate the product semantic bucket."""
    from backend.Services.step_parser import parse_step_with_pmi

    step = """ISO-10303-21;
HEADER;
FILE_SCHEMA(('AP242_MANAGED_MODEL_BASED_3D_ENGINEERING'));
ENDSEC;
DATA;
#1 = PRODUCT('P-100','Pump Housing','Demo housing',());
#2 = PRODUCT_DEFINITION_FORMATION('A','released revision',#1);
#3 = PRODUCT_DEFINITION('design','part view',#2,#4);
#4 = PRODUCT_DEFINITION_CONTEXT('part definition',#5,'design');
#5 = APPLICATION_CONTEXT('mechanical design');
ENDSEC;
END-ISO-10303-21;
"""

    step_path = tmp_path / "product_structure.stp"
    step_path.write_text(step, encoding="utf-8")

    doc = parse_step_with_pmi(step_path)

    assert len(doc.entities) == 5
    assert len(doc.cad_products) == 1
    assert doc.cad_products[0].entity_type == "PRODUCT"


def test_step_to_ttl_emits_ap242_semantic_graph(tmp_path):
    """STEP TTL should be valid RDF with AP242 classes, references, and part-model alignment."""
    from rdflib import Graph, Namespace
    from rdflib.namespace import OWL, RDF, RDFS, SKOS
    from backend.Services.owl_step_engine import convert_step_to_ttl

    step = """ISO-10303-21;
HEADER;
FILE_SCHEMA(('AP242_MANAGED_MODEL_BASED_3D_ENGINEERING_MIM_LF'));
ENDSEC;
DATA;
#1 = PRODUCT('P-100','Pump Housing','Demo housing',());
#2 = PRODUCT_DEFINITION_FORMATION('A','released revision',#1);
#3 = PRODUCT_DEFINITION('design','part view',#2,#4);
#4 = PRODUCT_DEFINITION_CONTEXT('part definition',#5,'design');
#5 = APPLICATION_CONTEXT('mechanical design');
#6 = GEOMETRIC_TOLERANCE('GT1','Position tolerance','controls hole',#3,#5);
ENDSEC;
END-ISO-10303-21;
"""

    step_path = tmp_path / "pump_housing.stp"
    ttl_path = tmp_path / "pump_housing.ttl"
    step_path.write_text(step, encoding="utf-8")

    result = convert_step_to_ttl(
        file_path=step_path,
        output_path=ttl_path,
        base_uri="http://example.org/step#",
        include_pmi=True,
        validate_against_domain=False,
        copy_reference_ontology=False,
    )

    assert result["success"] is True
    ttl = ttl_path.read_text(encoding="utf-8")
    assert "http://example.org/pmi#" not in ttl

    graph = Graph()
    graph.parse(str(ttl_path), format="turtle")

    inst = Namespace("http://example.org/step#")
    step_ns = Namespace("http://www.step-nc.org/step#")
    ap242 = Namespace("http://www.step-nc.org/ap242#")
    pmi = Namespace("http://depo-onto.local/ontology/pmi#")
    bom = Namespace("http://standards.iso.org/iso/ts/10303/-3001/-ed-2/tech/xml-schema/bo_model#")

    assert (inst.entity_1, RDF.type, OWL.NamedIndividual) in graph
    assert (inst.entity_1, RDF.type, step_ns.Entity) in graph
    assert (inst.entity_1, RDF.type, ap242.PRODUCT) in graph
    assert (ap242.PRODUCT, RDFS.subClassOf, step_ns.Entity) in graph
    assert (ap242.PRODUCT, step_ns.mapsToAp242BusinessObjectClass, bom.Part) in graph
    assert (ap242.PRODUCT, SKOS.closeMatch, bom.Part) in graph
    assert (inst.entity_2, step_ns.references, inst.entity_1) in graph
    assert (step_ns.references, RDF.type, OWL.ObjectProperty) in graph
    assert (step_ns.references, RDFS.domain, step_ns.Entity) in graph
    assert (step_ns.references, RDFS.range, step_ns.Entity) in graph
    assert (inst.tolerance_6, RDF.type, pmi.GeometricTolerance) in graph
    assert (inst.tolerance_6, pmi.tolerancedFeature, inst.entity_3) in graph


def test_step_mapping_catalog_matches_parser_and_ap242_part_model():
    """Mapping API should use parser-normalized AP242 tokens and the same part model as TTL generation."""
    from backend.Services.ontology_mapper_service import OntologyMapperService

    mappings = OntologyMapperService.get_mappings("step")
    by_source = {mapping["source_entity"]: mapping for mapping in mappings}

    assert "step:PRODUCT" in by_source
    assert "step:PRODUCT_DEFINITION_FORMATION" in by_source
    assert "step:PRODUCT_DEFINITION" in by_source
    assert "step:SHAPE_REPRESENTATION" in by_source
    assert "step:ProductDefinition" not in by_source
    assert by_source["step:PRODUCT"]["target_entity"] == "ap242:Part"
    assert by_source["step:PRODUCT_DEFINITION_FORMATION"]["target_entity"] == "ap242:PartVersion"
    assert by_source["step:PRODUCT_DEFINITION"]["target_entity"] == "ap242:PartView"
    assert by_source["step:SHAPE_REPRESENTATION"]["target_entity"] == "ap242:GeometricModel"

    dictionary = OntologyMapperService.get_data_dictionary("step")
    terms = {entry["term_id"] for entry in dictionary}
    assert {"step:PRODUCT", "step:PRODUCT_DEFINITION_FORMATION", "step:PRODUCT_DEFINITION", "step:SHAPE_REPRESENTATION"} <= terms


def test_step_import_schema_uses_entity_type_labels():
    """STEP import graph schema should label nodes by AP242 entity_type, not generic DataNode."""
    from backend.Services.unified_data_import import DataTransformer

    rows = [
        {"import_row_key": "#1", "id": "#1", "entity_type": "PRODUCT", "args": "'P-100'"},
        {"import_row_key": "#2", "id": "#2", "entity_type": "PRODUCT_DEFINITION", "args": "#1"},
        {"import_row_key": "#3", "id": "#3", "entity_type": "SHAPE_REPRESENTATION", "args": "#2"},
    ]

    schema = DataTransformer.auto_detect_schema(rows)
    labels = {node["label"] for node in schema["nodes"]}

    assert labels == {"PRODUCT", "PRODUCT_DEFINITION", "SHAPE_REPRESENTATION"}
    assert "DataNode" not in labels
    assert all(node["_filter_key"] == "entity_type" for node in schema["nodes"])


def test_ap242_bom_exp_is_used_for_domain_integration(monkeypatch, tmp_path):
    """AP242 SMRL v12 folders use bom.exp/bom.xsd, not DomainModel.exp only."""
    from backend.Services.owl_step_engine import _integrate_domain_models

    smrl_dir = tmp_path / "managed_model_based_3d_engineering"
    smrl_dir.mkdir()
    (smrl_dir / "bom.xsd").write_text(
        """<?xml version="1.0"?>
<xsd:schema xmlns:xsd="http://www.w3.org/2001/XMLSchema"
            targetNamespace="http://standards.iso.org/iso/ts/10303/-3001/-ed-2/tech/xml-schema/bo_model"
            version="2016-03-30"/>
""",
        encoding="utf-8",
    )
    (smrl_dir / "bom.exp").write_text(
        """SCHEMA managed_model_based_3d_engineering_bom;
ENTITY GeometricModel;
  id : STRING;
END_ENTITY;
ENTITY GeometricDimension;
  name : STRING;
END_ENTITY;
END_SCHEMA;
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("AP242_DOMAIN_MODEL_PATH", str(smrl_dir))

    ttl = _integrate_domain_models(
        "http://example.org/step#",
        "step",
        "AP242_MANAGED_MODEL_BASED_3D_ENGINEERING",
    )

    assert "bom.exp" in ttl
    assert "managed_model_based_3d_engineering_bom" in ttl
    assert "GeometricModel" in ttl
    assert "GeometricDimension" in ttl


def test_ap242_bom_is_found_under_repo_style_business_object_models(monkeypatch, tmp_path):
    """AP242 domain integration should discover bom.xsd/bom.exp in repo-style business_object_models folders."""
    from backend.Services import owl_step_engine

    repo_like_root = tmp_path / "repo_like_root"
    smrl_dir = repo_like_root / "data" / "business_object_models" / "managed_model_based_3d_engineering"
    smrl_dir.mkdir(parents=True)
    (smrl_dir / "bom.xsd").write_text(
        """<?xml version="1.0"?>
<xsd:schema xmlns:xsd="http://www.w3.org/2001/XMLSchema"
            targetNamespace="http://standards.iso.org/iso/ts/10303/-3001/-ed-2/tech/xml-schema/bo_model"
            version="2016-03-30"/>
""",
        encoding="utf-8",
    )
    (smrl_dir / "bom.exp").write_text(
        """SCHEMA managed_model_based_3d_engineering_bom;
ENTITY ShapeAspect;
  name : STRING;
END_ENTITY;
END_SCHEMA;
""",
        encoding="utf-8",
    )

    monkeypatch.setattr(owl_step_engine, "_configured_domain_model_path", lambda _default: repo_like_root)

    ttl = owl_step_engine._integrate_domain_models(
        "http://example.org/step#",
        "step",
        "AP242_MANAGED_MODEL_BASED_3D_ENGINEERING",
    )

    assert "bom.exp" in ttl
    assert "ShapeAspect" in ttl


def test_xsd_to_owl_generates_rich_semantics():
    """XSD conversion should emit classes, properties, subclassing, and cardinality."""
    from backend.Services.owl_generation_service import OWLGenerationService

    xsd = b"""<?xml version="1.0"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           targetNamespace="http://example.com/demo"
           xmlns="http://example.com/demo"
           elementFormDefault="qualified">
  <xs:complexType name="Part">
    <xs:sequence>
      <xs:element name="identifier" type="xs:string" minOccurs="1" maxOccurs="1"/>
      <xs:element name="child" type="Part" minOccurs="0" maxOccurs="unbounded"/>
    </xs:sequence>
    <xs:attribute name="revision" type="xs:string" use="required"/>
  </xs:complexType>
  <xs:complexType name="MachinedPart">
    <xs:complexContent>
      <xs:extension base="Part">
        <xs:sequence>
          <xs:element name="material" type="xs:string" minOccurs="0"/>
        </xs:sequence>
      </xs:extension>
    </xs:complexContent>
  </xs:complexType>
</xs:schema>
"""

    ttl, metadata = OWLGenerationService.generate_owl_from_xsd(xsd, "demo.xsd")

    assert metadata["format"] == "XSD"
    assert "owl:Class" in ttl
    assert "owl:ObjectProperty" in ttl
    assert "owl:DatatypeProperty" in ttl
    assert "rdfs:domain" in ttl
    assert "rdfs:range" in ttl
    assert "rdfs:subClassOf" in ttl
    assert "owl:minCardinality" in ttl
    assert "owl:maxCardinality" in ttl
    assert metadata.get("owlready2", {}).get("engine") == "owlready2"


def test_xsd_target_namespace_overrides_generated_fallback():
    """XSD targetNamespace should drive the generated ontology base URI."""
    from backend.Services.owl_generation_service import OWLGenerationService

    xsd = b"""<?xml version="1.0"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           targetNamespace="http://example.com/customer/schema"
           xmlns="http://example.com/customer/schema"
           elementFormDefault="qualified">
  <xs:complexType name="Thing">
    <xs:sequence>
      <xs:element name="name" type="xs:string" minOccurs="0"/>
    </xs:sequence>
  </xs:complexType>
</xs:schema>
"""

    ttl, metadata = OWLGenerationService.generate_owl_from_xsd(xsd, "customer_schema.xsd")

    assert metadata["target_namespace"] == "http://example.com/customer/schema"
    assert metadata["base_uri"] == "http://example.com/customer/schema#"
    assert metadata["ontology_prefix"] == "schema"
    assert "http://example.com/customer/schema#" in ttl
    assert "http://depo-onto.local/xsd#customer_schema/" not in ttl


def test_rdf_loader_preserves_ontology_relationships():
    """Neo4j push should preserve OWL classes/properties/domain/range/subclass semantics."""
    from rdflib import Graph
    from backend.Services.ontology_upload_manager import OntologyUploadManager

    ttl = """@prefix ex: <http://example.com/demo#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

ex:Part a owl:Class ; rdfs:label "Part" .
ex:MachinedPart a owl:Class ; rdfs:subClassOf ex:Part .
ex:hasChild a owl:ObjectProperty ; rdfs:domain ex:Part ; rdfs:range ex:Part .
ex:revision a owl:DatatypeProperty ; rdfs:domain ex:Part ; rdfs:range xsd:string .
"""
    rdf_graph = Graph()
    rdf_graph.parse(data=ttl, format="turtle")
    neo4j = MagicMock()
    neo4j.query.return_value = [{"count": 1}]

    result = OntologyUploadManager._push_rdf_graph_to_neo4j(
        ontology_id="demo_1",
        meta={"prefix": "demo", "ontology_name": "Demo", "version": 1},
        rdf_graph=rdf_graph,
        graph=neo4j,
        owl_file_path="demo.generated.ttl",
    )

    submitted_cypher = "\n".join(call.args[0] for call in neo4j.query.call_args_list)
    assert result["parsed_class_count"] == 2
    assert result["parsed_object_property_count"] == 1
    assert result["parsed_datatype_property_count"] == 1
    assert result["parsed_subclass_relationship_count"] == 1
    assert "SUBCLASS_OF" in submitted_cypher
    assert "DOMAIN" in submitted_cypher
    assert "RANGE" in submitted_cypher

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


def test_step_parser_preserves_ap242_compound_entity_types(tmp_path):
    """AP242 compound Part 21 instances should retain every top-level entity type."""
    from backend.Services.step_parser import iter_part21_entities, parse_step_with_pmi

    step = """ISO-10303-21;
HEADER;
FILE_SCHEMA(('AP242_MANAGED_MODEL_BASED_3D_ENGINEERING_MIM_LF'));
ENDSEC;
DATA;
#1 = PRODUCT('P-200','Compound Demo','Demo part',());
#2 = (REPRESENTATION_ITEM('axis') GEOMETRIC_REPRESENTATION_ITEM() CARTESIAN_POINT('axis origin',(0.0,0.0,0.0)));
#3 = (GEOMETRIC_TOLERANCE('GT-1','Position tolerance','compound tolerance',#2,#1) SHAPE_ASPECT_RELATIONSHIP('rel','',#1,#2));
ENDSEC;
END-ISO-10303-21;
"""
    path = tmp_path / "compound_ap242.stp"
    path.write_text(step, encoding="utf-8")

    entities = list(iter_part21_entities(path))
    compound_geometry = next(entity for entity in entities if entity.step_id == 2)
    compound_tolerance = next(entity for entity in entities if entity.step_id == 3)

    assert compound_geometry.entity_type == "REPRESENTATION_ITEM"
    assert compound_geometry.compound_entity_types == [
        "REPRESENTATION_ITEM",
        "GEOMETRIC_REPRESENTATION_ITEM",
        "CARTESIAN_POINT",
    ]
    assert "GEOMETRIC_TOLERANCE" in compound_tolerance.compound_entity_types

    doc = parse_step_with_pmi(path)
    assert any(item.id == 2 for item in doc.cad_representations)
    assert any(item.id == 3 for item in doc.geometric_tolerances)

    from backend.Services.unified_data_import import FileParser
    rows, stats = FileParser._parse_step(path.read_bytes())
    row_by_id = {row["id"]: row for row in rows}
    assert row_by_id["#2"]["compound_entity_types"] == compound_geometry.compound_entity_types
    assert stats["entity_types"]["REPRESENTATION_ITEM"] == 1


def test_step_to_ttl_types_compound_entities_with_all_ap242_classes(tmp_path):
    """Generated OWL/RDF should not collapse AP242 compound entities to only the first type."""
    from rdflib import Graph, Namespace
    from rdflib.namespace import RDF
    from backend.Services.owl_step_engine import convert_step_to_ttl

    step = """ISO-10303-21;
HEADER;
FILE_SCHEMA(('AP242_MANAGED_MODEL_BASED_3D_ENGINEERING_MIM_LF'));
ENDSEC;
DATA;
#2 = (REPRESENTATION_ITEM('axis') GEOMETRIC_REPRESENTATION_ITEM() CARTESIAN_POINT('axis origin',(0.0,0.0,0.0)));
ENDSEC;
END-ISO-10303-21;
"""
    path = tmp_path / "compound_export.stp"
    path.write_text(step, encoding="utf-8")

    ttl_path = tmp_path / "compound_export.ttl"
    metadata = convert_step_to_ttl(
        file_path=path,
        output_path=ttl_path,
        base_uri="http://example.com/ap242/compound#",
        namespace_prefix="cmp",
        include_pmi=True,
        validate_against_domain=False,
        copy_reference_ontology=False,
    )
    graph = Graph().parse(str(ttl_path), format="turtle")
    inst = Namespace("http://example.com/ap242/compound#")
    ap242 = Namespace("http://www.step-nc.org/ap242#")

    assert metadata["success"] is True
    assert (inst.entity_2, RDF.type, ap242.REPRESENTATION_ITEM) in graph
    assert (inst.entity_2, RDF.type, ap242.GEOMETRIC_REPRESENTATION_ITEM) in graph
    assert (inst.entity_2, RDF.type, ap242.CARTESIAN_POINT) in graph


