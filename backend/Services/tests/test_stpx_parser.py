from pathlib import Path

from backend.Services.unified_data_import import FileParser
from backend.Services.step_parser import detect_step_format, get_pmi_summary, iter_part21_entities, parse_step_metadata, parse_step_with_pmi


def test_stpx_streaming_parser_preserves_identifiers_refs_and_text(tmp_path: Path):
    stpx = """<?xml version="1.0" encoding="UTF-8"?>
<Uos xmlns="http://standards.iso.org/iso/ts/10303/-3001/-ed-1/tech/xml-schema/bo_model"
     xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
     xsi:schemaLocation="http://standards.iso.org/iso/ts/10303/-3001/-ed-1/tech/xml-schema/bo_model bom.xsd">
  <Header>
    <Name>Example STPX</Name>
  </Header>
  <Part uid="part-1" id="PartOne" type="n0:PartType">
    <Name>Motor Assembly</Name>
    <Occurrence uid="occ-1" uidRef="part-1" idContextRef="ctx-1">
      <Identifier>OCC-1</Identifier>
    </Occurrence>
  </Part>
</Uos>
"""
    path = tmp_path / "sample.stpx"
    path.write_text(stpx, encoding="utf-8")

    assert detect_step_format(path) == "stpx"
    meta = parse_step_metadata(path)
    assert meta.format == "stpx"
    assert meta.file_schema == "bo_model"

    entities = list(iter_part21_entities(path))
    assert len(entities) >= 5
    assert any(e.entity_type == "PART" and e.source_identifier == "PartOne" for e in entities)
    assert any(e.entity_type == "OCCURRENCE" and e.ref_ids for e in entities)
    assert any(e.text_value == "Motor Assembly" for e in entities)

    rows, stats = FileParser._parse_step(path.read_bytes())
    assert rows
    assert stats["format"] == "STEP"
    assert stats["unresolved_reference_count"] >= 1
    assert stats["semantic_role_counts"]["product"] >= 1
    assert stats["semantic_role_counts"]["topology"] >= 1
    assert stats["cad_business_object_count"] >= 2
    part_rows = [row for row in rows if row.get("entity_type") == "PART"]
    assert part_rows
    assert part_rows[0]["semantic_role"] == "product"
    assert part_rows[0]["is_cad_business_object"] is True
    assert part_rows[0]["external_id"] == "PartOne"
    assert part_rows[0]["name"] == "Motor Assembly"
    occurrence_rows = [row for row in rows if row.get("entity_type") == "OCCURRENCE"]
    assert occurrence_rows
    assert occurrence_rows[0]["semantic_role"] == "topology"
    assert occurrence_rows[0]["uidRef"] == "part-1"
    assert occurrence_rows[0]["parent_step_id"].startswith("#")


def test_stpx_bo_model_entities_are_classified_as_cad_business_objects(tmp_path: Path):
    stpx = """<?xml version="1.0" encoding="UTF-8"?>
<Uos xmlns="http://standards.iso.org/iso/ts/10303/-3001/-ed-1/tech/xml-schema/bo_model"
     xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
     xsi:schemaLocation="http://standards.iso.org/iso/ts/10303/-3001/-ed-1/tech/xml-schema/bo_model bom.xsd">
  <Part uid="part-1" id="PartOne" type="n0:PartType">
    <PartVersion uid="version-1" id="PartOne/A"/>
    <PartView uid="view-1" id="PartOne/design">
      <Occurrence uid="occ-1" uidRef="part-1"/>
    </PartView>
    <Placement uid="plc-1"/>
    <CartesianTransformation uid="xf-1"/>
    <RotationMatrix uid="rot-1"/>
    <TranslationVector uid="vec-1"/>
  </Part>
</Uos>
"""
    path = tmp_path / "bo_model_sample.stpx"
    path.write_text(stpx, encoding="utf-8")

    doc = parse_step_with_pmi(path)

    product_types = {item.entity_type for item in doc.cad_products}
    representation_types = {item.entity_type for item in doc.cad_representations}
    topology_types = {item.entity_type for item in doc.cad_topology}
    geometry_types = {item.entity_type for item in doc.cad_geometry}

    assert {"PART", "PART_VERSION"} <= product_types
    assert "PART_VIEW" in representation_types
    assert "OCCURRENCE" in topology_types
    assert {"PLACEMENT", "CARTESIAN_TRANSFORMATION", "ROTATION_MATRIX", "TRANSLATION_VECTOR"} <= geometry_types
    assert any(item.external_id == "PartOne" and item.name == "PartOne" for item in doc.cad_products)

    rows, stats = FileParser._parse_step(path.read_bytes())
    by_type = {row["entity_type"]: row for row in rows}
    assert by_type["ROTATION_MATRIX"]["semantic_role"] == "geometry"
    assert by_type["ROTATION_MATRIX"]["is_cad_business_object"] is True
    assert by_type["TRANSLATION_VECTOR"]["semantic_role"] == "geometry"
    assert stats["semantic_role_counts"]["geometry"] >= 4


def test_step_shape_entities_are_cad_business_objects(tmp_path: Path):
    step = """ISO-10303-21;
HEADER;
FILE_SCHEMA(('AP242_MANAGED_MODEL_BASED_3D_ENGINEERING'));
ENDSEC;
DATA;
#1 = PRODUCT('P-1','Pump housing','',());
#2 = PRODUCT_DEFINITION('design','',#1,#10);
#3 = PRODUCT_DEFINITION_SHAPE('shape for pump','',#2);
#4 = SHAPE_ASPECT('mounting face','',#3,.T.);
#5 = SHAPE_REPRESENTATION('body shape',(),#20);
ENDSEC;
END-ISO-10303-21;
"""
    path = tmp_path / "shape_sample.stp"
    path.write_text(step, encoding="utf-8")

    rows, stats = FileParser._parse_step(path.read_bytes())
    by_type = {row["entity_type"]: row for row in rows}

    assert by_type["PRODUCT_DEFINITION_SHAPE"]["semantic_role"] == "shape"
    assert by_type["PRODUCT_DEFINITION_SHAPE"]["is_cad_business_object"] is True
    assert by_type["SHAPE_ASPECT"]["semantic_role"] == "feature"
    assert by_type["SHAPE_REPRESENTATION"]["semantic_role"] == "representation"
    assert stats["semantic_role_counts"]["shape"] == 1
    assert stats["semantic_role_counts"]["feature"] == 1


def test_step_pmi_tolerance_roles_take_precedence_over_geometry(tmp_path: Path):
    step = """ISO-10303-21;
HEADER;
FILE_SCHEMA(('AP242_MANAGED_MODEL_BASED_3D_ENGINEERING'));
ENDSEC;
DATA;
#1 = PRODUCT('P-1','Pump housing','',());
#2 = SHAPE_ASPECT('hole diameter','',#1,.T.);
#3 = GEOMETRIC_TOLERANCE('GT-1','Position tolerance','controls hole',#2,#1);
#4 = DIMENSIONAL_SIZE(#2,'diameter');
#5 = LENGTH_MEASURE_WITH_UNIT(LENGTH_MEASURE(-0.2),#9);
#6 = LENGTH_MEASURE_WITH_UNIT(LENGTH_MEASURE(0.05),#9);
#7 = TOLERANCE_VALUE(#5,#6);
#8 = PLUS_MINUS_TOLERANCE(#7,#4);
#9 = SI_UNIT(.MILLI.,.METRE.);
ENDSEC;
END-ISO-10303-21;
"""
    path = tmp_path / "pmi_tolerance_sample.stp"
    path.write_text(step, encoding="utf-8")

    rows, stats = FileParser._parse_step(path.read_bytes())
    by_type = {row["entity_type"]: row for row in rows}

    assert by_type["GEOMETRIC_TOLERANCE"]["semantic_role"] == "geometric_tolerance"
    assert by_type["GEOMETRIC_TOLERANCE"]["is_cad_business_object"] is True
    assert by_type["PLUS_MINUS_TOLERANCE"]["semantic_role"] == "dimension_tolerance"
    assert by_type["TOLERANCE_VALUE"]["semantic_role"] == "dimension_tolerance"
    assert stats["semantic_role_counts"]["geometric_tolerance"] == 1
    assert stats["semantic_role_counts"]["dimension_tolerance"] == 2


def test_step_feature_and_annotation_roles_are_import_visible(tmp_path: Path):
    step = """ISO-10303-21;
HEADER;
FILE_SCHEMA(('AP242_MANAGED_MODEL_BASED_3D_ENGINEERING'));
ENDSEC;
DATA;
#1 = PRODUCT('P-1','Pump housing','',());
#2 = SHAPE_ASPECT('mounting feature','',#1,.T.);
#3 = FEATURE_COMPONENT_DEFINITION('boss feature','',#2);
#4 = DRAUGHTING_CALLOUT('hole note',(#5));
#5 = TEXT_LITERAL('Tighten evenly',#6,'LEFT',.LEFT.);
#6 = AXIS2_PLACEMENT_3D('origin',#7,#8,#9);
ENDSEC;
END-ISO-10303-21;
"""
    path = tmp_path / "feature_annotation_sample.stp"
    path.write_text(step, encoding="utf-8")

    rows, stats = FileParser._parse_step(path.read_bytes())
    by_type = {row["entity_type"]: row for row in rows}

    assert by_type["SHAPE_ASPECT"]["semantic_role"] == "feature"
    assert by_type["FEATURE_COMPONENT_DEFINITION"]["semantic_role"] == "feature"
    assert by_type["DRAUGHTING_CALLOUT"]["semantic_role"] == "annotation"
    assert by_type["TEXT_LITERAL"]["semantic_role"] == "annotation"
    assert stats["semantic_role_counts"]["feature"] == 2
    assert stats["semantic_role_counts"]["annotation"] == 2


def test_step_extension_uses_same_part21_semantic_classification(tmp_path: Path):
    from backend.Services.unified_data_import import FileFormatDetector, FileType

    step = """ISO-10303-21;
HEADER;
FILE_SCHEMA(('AP242_MANAGED_MODEL_BASED_3D_ENGINEERING'));
ENDSEC;
DATA;
#1 = PRODUCT('P-1','Pump housing','',());
#2 = PRODUCT_DEFINITION_SHAPE('shape for pump','',#1);
#3 = SHAPE_ASPECT('mounting face','',#2,.T.);
#4 = ROTATION_MATRIX('rotation',(),());
#5 = GEOMETRIC_TOLERANCE('GT-1','Position tolerance','controls hole',#3,#4);
#6 = DRAUGHTING_CALLOUT('hole note',(#7));
#7 = TEXT_LITERAL('Tighten evenly',#4,'LEFT',.LEFT.);
ENDSEC;
END-ISO-10303-21;
"""
    path = tmp_path / "semantic_sample.step"
    path.write_text(step, encoding="utf-8")

    assert detect_step_format(path) == "p21"
    assert FileFormatDetector.detect(path.name) == FileType.STEP

    rows, stats = FileParser._parse_step(path.read_bytes())
    by_type = {row["entity_type"]: row for row in rows}

    assert by_type["PRODUCT"]["semantic_role"] == "product"
    assert by_type["PRODUCT_DEFINITION_SHAPE"]["semantic_role"] == "shape"
    assert by_type["SHAPE_ASPECT"]["semantic_role"] == "feature"
    assert by_type["ROTATION_MATRIX"]["semantic_role"] == "geometry"
    assert by_type["GEOMETRIC_TOLERANCE"]["semantic_role"] == "geometric_tolerance"
    assert by_type["DRAUGHTING_CALLOUT"]["semantic_role"] == "annotation"
    assert stats["cad_business_object_count"] >= 6


def test_step_pmi_associations_and_graphic_views_are_typed(tmp_path: Path):
    step = """ISO-10303-21;
HEADER;
FILE_SCHEMA(('AP242_MANAGED_MODEL_BASED_3D_ENGINEERING'));
ENDSEC;
DATA;
#1 = PRODUCT('P-1','Pump housing','',());
#2 = SHAPE_ASPECT('mounting face','',#1,.T.);
#3 = DATUM_FEATURE('A datum',#2);
#4 = GEOMETRIC_TOLERANCE('GT-1','Position tolerance','',#2,#3);
#5 = LEADER_CURVE('leader',#2);
#6 = ANNOTATION_OCCURRENCE('note',#5,#2,#7);
#7 = ANNOTATION_PLANE('MBD_A',#2);
#8 = DRAUGHTING_CALLOUT('callout',#6,#7);
ENDSEC;
END-ISO-10303-21;
"""
    path = tmp_path / "graphic_pmi_sample.stp"
    path.write_text(step, encoding="utf-8")

    doc = parse_step_with_pmi(path)

    tolerance = doc.geometric_tolerances[0]
    assert tolerance.toleranced_feature_refs == [2]
    assert tolerance.datum_system_refs == [3]

    annotation = next(item for item in doc.annotations if item.id == 6)
    assert annotation.feature_refs == [2]
    assert annotation.leader_refs == [5]
    assert annotation.view_refs == [7]

    assert any(item.id == 6 for item in doc.graphic_presentations)
    assert any(item.id == 7 for item in doc.saved_views)
    summary = get_pmi_summary(doc)
    assert summary["graphic_presentations"] >= 2
    assert summary["saved_views"] == 1
