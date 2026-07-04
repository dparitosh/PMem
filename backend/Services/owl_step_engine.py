"""
STEP to OWL ontology conversion engine.

Converts STEP (.stp, .step, .stpx) files to TTL/OWL format with:
- Basic STEP entity mapping to OWL classes
- PMI (Product Manufacturing Information) ontology generation
- AP203/AP214/AP242 schema compliance
- Domain model integration for validation

Integration of lightweight external parser + enhanced PMI parser.
"""

import os
import time
from pathlib import Path
from typing import Optional, Dict, Any, List
from loguru import logger
import shutil
from urllib.parse import quote

try:
    from rdflib import Graph, Literal, Namespace, URIRef
    from rdflib.namespace import DCTERMS, OWL, RDF, RDFS, SKOS, XSD
    _RDFLIB_IMPORT_ERROR = None
except ModuleNotFoundError as exc:
    Graph = None  # type: ignore[assignment]
    Literal = str  # type: ignore[assignment]
    Namespace = str  # type: ignore[assignment]
    URIRef = str  # type: ignore[assignment]
    DCTERMS = OWL = RDF = RDFS = SKOS = XSD = None  # type: ignore[assignment]
    _RDFLIB_IMPORT_ERROR = exc

try:
    from .ap242_domain_model import (
        AP242_MBD_BOM_NAMESPACE,
        describe_ap242_domain_model,
        describe_ap242_mbd_bom,
    )
except ImportError:
    from ap242_domain_model import (  # type: ignore
        AP242_MBD_BOM_NAMESPACE,
        describe_ap242_domain_model,
        describe_ap242_mbd_bom,
    )

# Paths adjusted for backend Services layout
_BACKEND_DIR = Path(__file__).resolve().parent.parent
_DEFAULT_STP_OUTPUT = _BACKEND_DIR / "output" / "stp"
_REFERENCE_ONTOLOGY_SRC = _BACKEND_DIR / "ontologies" / "generated"
_AP242_ONTO_URI = URIRef("http://IAE-depo.com/ap242-ontology")
_AP242_PACKAGE_MODE = os.getenv("AP242_REFERENCE_PACKAGE", "full").strip().lower()
_STEP_NS_URI = "http://www.step-nc.org/step#"
_AP242_NS_URI = "http://www.step-nc.org/ap242#"
_PMI_NS_URI = "http://depo-onto.local/ontology/pmi#"
_PROV_NS_URI = "http://www.w3.org/ns/prov#"
_BOM_NS_URI = AP242_MBD_BOM_NAMESPACE.rstrip("/") + "#"
_STEP = Namespace(_STEP_NS_URI)
_AP242 = Namespace(_AP242_NS_URI)
_PMI = Namespace(_PMI_NS_URI)
_BOM = Namespace(_BOM_NS_URI)
_PROV = Namespace(_PROV_NS_URI)

_AP242_PART_DATA_MODEL_MAPPINGS = {
    "PRODUCT": "Part",
    "PRODUCT_DEFINITION_FORMATION": "PartVersion",
    "PRODUCT_DEFINITION_FORMATION_WITH_SPECIFIED_SOURCE": "PartVersion",
    "PRODUCT_DEFINITION": "PartView",
    "PRODUCT_DEFINITION_SHAPE": "PartShapeElement",
    "NEXT_ASSEMBLY_USAGE_OCCURRENCE": "PartViewRelationship",
    "ASSEMBLY_COMPONENT_USAGE": "PartViewRelationship",
    "SHAPE_REPRESENTATION": "GeometricModel",
    "ADVANCED_BREP_SHAPE_REPRESENTATION": "GeometricModel",
    "GEOMETRIC_REPRESENTATION_CONTEXT": "GeometricContext",
    "DIMENSIONAL_SIZE": "GeometricDimension",
    "DIMENSIONAL_LOCATION": "GeometricDimension",
    "GEOMETRIC_TOLERANCE": "GeometricTolerance",
    "DATUM_FEATURE": "DatumFeature",
    "DATUM": "Datum",
}


def _read_backend_env_value(key: str) -> str:
    env_path = _BACKEND_DIR / ".env"
    if not env_path.exists():
        return ""
    try:
        for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            env_key, value = stripped.split("=", 1)
            if env_key.strip() == key:
                return value.strip().strip('"').strip("'")
    except Exception:
        return ""
    return ""


def _configured_domain_model_path(default_path: Path) -> Path:
    configured = (
        os.getenv("AP242_DOMAIN_MODEL_PATH")
        or os.getenv("DOMAIN_MODEL_PATH")
        or _read_backend_env_value("AP242_DOMAIN_MODEL_PATH")
        or _read_backend_env_value("DOMAIN_MODEL_PATH")
    )
    return Path(configured) if configured else default_path

# Import STEP parser from backend Services
try:
    from .step_parser import (  # noqa: F401
        parse_step_with_pmi,
        StepPMIDocument,
        StepFileMeta,
        StepP21Entity,
        get_pmi_summary,
        detect_step_format as external_detect_format,
        parse_step_metadata as external_parse_metadata,
        iter_part21_entities as external_iter_entities,
    )
    # noqa: F401
except ImportError:
    from step_parser import (  # type: ignore
        parse_step_with_pmi,
        StepPMIDocument,
        StepFileMeta,
        get_pmi_summary,
        detect_step_format as external_detect_format,
        parse_step_metadata as external_parse_metadata,
        iter_part21_entities as external_iter_entities,
    )


def convert_step_to_ttl(file_path: Path, output_path: Optional[Path] = None,
                       base_uri: str = "http://example.org/step#",
                       namespace_prefix: str = "step",
                       include_pmi: bool = True,
                       validate_against_domain: bool = True,
                       copy_reference_ontology: bool = True) -> Dict[str, Any]:
    """
    Convert STEP file to TTL ontology format.
    
    Args:
        file_path: Path to STEP file (.stp/.step/.stpx)
        output_path: Output TTL file path (auto-generated if None)
        base_uri: Base URI for generated ontology
        namespace_prefix: Namespace prefix for STEP entities
        include_pmi: Include PMI (Product Manufacturing Information) extraction
        validate_against_domain: Validate against domain models if available
        copy_reference_ontology: Copy shared AP242 ontology/shapes beside output
        
    Returns:
        Dict with conversion statistics and metadata
    """
    start_time = time.time()
    
    try:
        logger.info(f"Converting STEP file to TTL: {file_path.name}")
        
        # Auto-generate output path if not provided — always inside project output/stp/
        if output_path is None:
            _DEFAULT_STP_OUTPUT.mkdir(parents=True, exist_ok=True)
            output_path = _DEFAULT_STP_OUTPUT / f"{file_path.stem}.ttl"
        
        # Enhanced format detection using both parsers
        format_detected = _enhanced_format_detection(file_path)
        logger.info(f"Detected STEP format: {format_detected}")
        
        # Parse metadata using enhanced approach
        metadata = _parse_enhanced_metadata(file_path, format_detected)
        
        # Statistics tracking
        stats = {
            "format": format_detected,
            "schema": metadata.file_schema,
            "entities_processed": 0,
            "pmi_elements": 0,
            "classes_generated": 0,
            "properties_generated": 0,
            "individuals_generated": 0,
            "processing_time": 0
        }
        
        pmi_doc = None
        entities: List[StepP21Entity] = []
        if include_pmi:
            # Use enhanced PMI parser for comprehensive extraction
            logger.info("Extracting PMI data using enhanced parser...")
            pmi_doc = parse_step_with_pmi(file_path)
            entities = list(pmi_doc.entities)
            
            pmi_stats = get_pmi_summary(pmi_doc)
            stats.update({
                "entities_processed": len(pmi_doc.entities),
                "pmi_elements": sum([
                    len(pmi_doc.geometric_tolerances),
                    len(pmi_doc.datums), 
                    len(pmi_doc.dimensions),
                    len(pmi_doc.annotations)
                ]),
                "pmi_details": pmi_stats
            })
        else:
            # Use lightweight parser for basic entity extraction
            logger.info("Extracting basic entities using lightweight parser...")
            entities = list(external_iter_entities(file_path))
            stats["entities_processed"] = len(entities)
        
        ttl_content = _generate_step_rdf_ttl(
            entities=entities,
            metadata=metadata,
            base_uri=base_uri,
            namespace_prefix=namespace_prefix,
            pmi_doc=pmi_doc,
        )
        
        # Domain model validation (if requested and available)
        if validate_against_domain:
            ttl_content += _integrate_domain_models(base_uri, namespace_prefix, metadata.file_schema)
        
        # Write TTL file
        output_path.write_text(ttl_content, encoding='utf-8')

        copied_refs: Dict[str, Path] = {}
        if copy_reference_ontology:
            copied_refs = copy_ap242_reference_ontology(output_path.parent)
        
        stats.update({
            "processing_time": time.time() - start_time,
            "output_file": str(output_path),
            "ttl_size": len(ttl_content),
            "classes_generated": _count_ttl_classes(ttl_content),
            "properties_generated": _count_ttl_properties(ttl_content),
            "individuals_generated": _count_ttl_individuals(ttl_content),
            "reference_ontology_ttl": str(copied_refs.get("ontology_ttl", "")),
            "reference_ontology_owl": str(copied_refs.get("ontology_owl", "")),
            "reference_shapes_ttl": str(copied_refs.get("shapes_ttl", "")),
            "reference_alignment_ttl": str(copied_refs.get("alignment_ttl", "")),
            "reference_alignment_owl": str(copied_refs.get("alignment_owl", "")),
            "reference_mbd3d_model_ttl": str(copied_refs.get("mbd3d_model_ttl", "")),
            "reference_mbd3d_model_owl": str(copied_refs.get("mbd3d_model_owl", "")),
        })
        
        logger.info(f"STEP to TTL conversion completed: {stats}")
        return {"success": True, "stats": stats}
        
    except Exception as e:
        logger.error(f"STEP to TTL conversion failed: {e}")
        return {"success": False, "error": str(e)}


def _enhanced_format_detection(file_path: Path) -> str:
    """Enhanced format detection using both parsers."""
    # Use external parser's robust detection first
    external_format = external_detect_format(file_path)
    
    # Validate with additional checks
    suffix = file_path.suffix.lower()
    if external_format == "unknown" and suffix in {".stp", ".step", ".stpx"}:
        logger.warning(f"External parser couldn't detect format for {suffix}, using suffix-based detection")
        return "p21" if suffix in {".stp", ".step"} else "stpx"
    
    return external_format


def _parse_enhanced_metadata(file_path: Path, format_type: str) -> StepFileMeta:
    """Parse metadata using both parsers with fallback."""
    try:
        # Try external parser first (more robust for edge cases)
        return external_parse_metadata(file_path)
    except Exception as e:
        logger.warning(f"External metadata parsing failed: {e}, using basic detection")
        return StepFileMeta(
            format=format_type,
            file_schema=None,
            file_name=file_path.name
        )


def _as_namespace_uri(base_uri: str) -> str:
    """Return a URI namespace safe enough for generated local names."""
    cleaned = (base_uri or "http://depo-onto.local/step#").strip()
    if not cleaned:
        cleaned = "http://depo-onto.local/step#"
    if not cleaned.endswith(("#", "/")):
        cleaned += "#"
    return quote(cleaned, safe=":/#%?=&")


def _entity_uri(instance_ns: Namespace, step_id: int) -> URIRef:
    return instance_ns[f"entity_{step_id}"]


def _literal_if_value(graph: Graph, subject: URIRef, predicate: URIRef, value: Any, datatype: Optional[URIRef] = None) -> None:
    if value is None:
        return
    if isinstance(value, str) and value == "":
        return
    graph.add((subject, predicate, Literal(value, datatype=datatype)))


def _display_label(entity_type: str) -> str:
    return (entity_type or "").replace("_", " ").title()

def _entity_type_candidates(entity: StepP21Entity) -> List[str]:
    candidates = [getattr(entity, "entity_type", ""), *getattr(entity, "compound_entity_types", [])]
    seen = set()
    ordered: List[str] = []
    for candidate in candidates:
        normalized = str(candidate or "").strip().upper()
        if normalized and normalized not in seen:
            seen.add(normalized)
            ordered.append(normalized)
    return ordered


def _declare_class(graph: Graph, class_uri: URIRef, label: str, parent: Optional[URIRef] = None, comment: str = "") -> None:
    graph.add((class_uri, RDF.type, OWL.Class))
    graph.add((class_uri, RDFS.label, Literal(label)))
    if parent is not None:
        graph.add((class_uri, RDFS.subClassOf, parent))
    if comment:
        graph.add((class_uri, RDFS.comment, Literal(comment)))


def _declare_object_property(graph: Graph, prop: URIRef, label: str, domain: URIRef, range_: URIRef, comment: str = "") -> None:
    graph.add((prop, RDF.type, OWL.ObjectProperty))
    graph.add((prop, RDFS.label, Literal(label)))
    graph.add((prop, RDFS.domain, domain))
    graph.add((prop, RDFS.range, range_))
    if comment:
        graph.add((prop, RDFS.comment, Literal(comment)))


def _declare_datatype_property(graph: Graph, prop: URIRef, label: str, domain: URIRef, range_: URIRef, comment: str = "") -> None:
    graph.add((prop, RDF.type, OWL.DatatypeProperty))
    graph.add((prop, RDFS.label, Literal(label)))
    graph.add((prop, RDFS.domain, domain))
    graph.add((prop, RDFS.range, range_))
    if comment:
        graph.add((prop, RDFS.comment, Literal(comment)))


def _add_ref_links(graph: Graph, subject: URIRef, refs: List[int], entity_map: Dict[int, StepP21Entity], instance_ns: Namespace, predicate: URIRef) -> None:
    for ref_id in sorted(set(refs or [])):
        target = _entity_uri(instance_ns, ref_id)
        graph.add((subject, predicate, target))
        if ref_id not in entity_map:
            graph.add((target, RDF.type, OWL.NamedIndividual))
            graph.add((target, RDF.type, _STEP.Entity))
            graph.add((target, RDFS.label, Literal(f"Unresolved STEP reference #{ref_id}")))
            graph.add((target, _STEP.stepId, Literal(ref_id, datatype=XSD.integer)))


def _generate_step_rdf_ttl(
    entities: List[StepP21Entity],
    metadata: StepFileMeta,
    base_uri: str,
    namespace_prefix: str,
    pmi_doc: Optional[StepPMIDocument] = None,
) -> str:
    """Generate AP242-aligned STEP instance ontology using rdflib."""
    if Graph is None:
        raise RuntimeError(
            "rdflib is required for STEP/AP242 ontology generation. "
            "Run backend\\setup.bat --backend or install backend requirements."
        ) from _RDFLIB_IMPORT_ERROR

    instance_ns = Namespace(_as_namespace_uri(base_uri))
    prefix = (namespace_prefix or "inst").strip() or "inst"
    if prefix in {"rdf", "rdfs", "owl", "xsd", "sh", "skos", "dcterms", "prov", "step", "ap242", "pmi", "bom"}:
        prefix = "inst"

    graph = Graph()
    graph.bind(prefix, instance_ns)
    graph.bind("step", _STEP)
    graph.bind("ap242", _AP242)
    graph.bind("pmi", _PMI)
    graph.bind("bom", _BOM)
    graph.bind("skos", SKOS)
    graph.bind("dcterms", DCTERMS)
    graph.bind("prov", _PROV)

    ontology_uri = URIRef(str(instance_ns))
    graph.add((ontology_uri, RDF.type, OWL.Ontology))
    graph.add((ontology_uri, RDFS.label, Literal("AP242 STEP Instance Ontology")))
    graph.add((ontology_uri, RDFS.comment, Literal(f"Generated from STEP file: {metadata.file_name}")))
    graph.add((ontology_uri, OWL.imports, _AP242_ONTO_URI))
    graph.add((ontology_uri, OWL.imports, URIRef(_AP242_NS_URI)))
    graph.add((ontology_uri, OWL.versionInfo, Literal("2.0")))
    _literal_if_value(graph, ontology_uri, _STEP.fileSchema, metadata.file_schema)
    _literal_if_value(graph, ontology_uri, _STEP.schemaNamespace, metadata.namespace)
    _literal_if_value(graph, ontology_uri, _STEP.schemaLocation, metadata.schema_location)
    _literal_if_value(graph, ontology_uri, _STEP.schemaVersion, metadata.schema_version)
    _literal_if_value(graph, ontology_uri, _STEP.sourceFormat, metadata.format)

    _declare_class(
        graph,
        _STEP.Entity,
        "STEP Entity",
        OWL.Thing,
        "A concrete entity instance parsed from an ISO 10303 Part 21 or Part 28 exchange file.",
    )
    _declare_class(graph, _PMI.GeometricTolerance, "Geometric Tolerance", _STEP.Entity)
    _declare_class(graph, _PMI.Datum, "Datum", _STEP.Entity)
    _declare_class(graph, _PMI.Dimension, "Dimension", _STEP.Entity)
    _declare_class(graph, _PMI.Annotation, "Annotation", _STEP.Entity)
    _declare_class(graph, _PMI.SurfaceFinish, "Surface Finish", _STEP.Entity)

    _declare_object_property(
        graph,
        _STEP.references,
        "references",
        _STEP.Entity,
        _STEP.Entity,
        "Preserves STEP #id references as RDF object edges for traceability and graph traversal.",
    )
    _declare_object_property(
        graph,
        _STEP.mapsToAp242BusinessObjectClass,
        "maps to AP242 business object class",
        OWL.Class,
        OWL.Class,
        "Alignment from AP242 AIM/STEP entity classes to AP242 MBD business-object data model classes.",
    )
    _declare_object_property(graph, _STEP.representsStepEntity, "represents STEP entity", OWL.Thing, _STEP.Entity)
    _declare_datatype_property(graph, _STEP.stepId, "STEP id", _STEP.Entity, XSD.integer)
    _declare_datatype_property(graph, _STEP.entityType, "STEP entity type", _STEP.Entity, XSD.string)
    _declare_datatype_property(graph, _STEP.rawArgs, "raw STEP arguments", _STEP.Entity, XSD.string)
    _declare_datatype_property(graph, _STEP.fileSchema, "STEP file schema", OWL.Thing, XSD.string)
    _declare_datatype_property(graph, _STEP.sourceFormat, "STEP source format", OWL.Thing, XSD.string)

    for prop, label, range_class in [
        (_PMI.tolerancedFeature, "toleranced feature", _STEP.Entity),
        (_PMI.datumSystem, "datum system", _STEP.Entity),
        (_PMI.datumFeature, "datum feature", _STEP.Entity),
        (_PMI.measuredFeature, "measured feature", _STEP.Entity),
        (_PMI.presentationReference, "presentation reference", _STEP.Entity),
        (_PMI.leaderReference, "leader reference", _STEP.Entity),
    ]:
        _declare_object_property(graph, prop, label, OWL.Thing, range_class)

    for prop, label, domain, range_ in [
        (_PMI.toleranceType, "tolerance type", _PMI.GeometricTolerance, XSD.string),
        (_PMI.magnitude, "magnitude", _PMI.GeometricTolerance, XSD.double),
        (_PMI.unit, "unit", OWL.Thing, XSD.string),
        (_PMI.datumLabel, "datum label", _PMI.Datum, XSD.string),
        (_PMI.dimensionType, "dimension type", _PMI.Dimension, XSD.string),
        (_PMI.nominalValue, "nominal value", _PMI.Dimension, XSD.double),
        (_PMI.lowerTolerance, "lower tolerance", _PMI.Dimension, XSD.double),
        (_PMI.upperTolerance, "upper tolerance", _PMI.Dimension, XSD.double),
        (_PMI.annotationType, "annotation type", _PMI.Annotation, XSD.string),
        (_PMI.textContent, "text content", _PMI.Annotation, XSD.string),
    ]:
        _declare_datatype_property(graph, prop, label, domain, range_)

    entity_map = {entity.step_id: entity for entity in entities}
    encountered_types = sorted({etype for entity in entities for etype in _entity_type_candidates(entity)})
    for entity_type in encountered_types:
        ap242_class = _AP242[entity_type]
        _declare_class(
            graph,
            ap242_class,
            _display_label(entity_type),
            _STEP.Entity,
            f"AP242/STEP entity class generated from encountered entity type {entity_type}.",
        )
        graph.add((ap242_class, SKOS.notation, Literal(entity_type)))
        mapped_bom_class = _AP242_PART_DATA_MODEL_MAPPINGS.get(entity_type)
        if mapped_bom_class:
            bom_class = _BOM[mapped_bom_class]
            _declare_class(graph, bom_class, mapped_bom_class, OWL.Thing)
            graph.add((ap242_class, _STEP.mapsToAp242BusinessObjectClass, bom_class))
            graph.add((ap242_class, SKOS.closeMatch, bom_class))

    for entity in entities:
        subject = _entity_uri(instance_ns, entity.step_id)
        entity_types = _entity_type_candidates(entity) or [entity.entity_type]
        graph.add((subject, RDF.type, OWL.NamedIndividual))
        graph.add((subject, RDF.type, _STEP.Entity))
        for entity_type in entity_types:
            graph.add((subject, RDF.type, _AP242[entity_type]))
            mapped_bom_class = _AP242_PART_DATA_MODEL_MAPPINGS.get(entity_type)
            if mapped_bom_class:
                graph.add((subject, RDF.type, _BOM[mapped_bom_class]))
        graph.add((subject, RDFS.label, Literal(f"#{entity.step_id} {entity.entity_type}")))
        graph.add((subject, SKOS.notation, Literal(f"#{entity.step_id}")))
        graph.add((subject, _STEP.stepId, Literal(entity.step_id, datatype=XSD.integer)))
        graph.add((subject, _STEP.entityType, Literal(entity.entity_type)))
        for compound_type in getattr(entity, "compound_entity_types", []) or []:
            graph.add((subject, _STEP.entityType, Literal(compound_type)))
        graph.add((subject, _STEP.rawArgs, Literal((entity.raw_args or "")[:1000])))
        _literal_if_value(graph, subject, _STEP.fileSchema, metadata.file_schema)
        _literal_if_value(graph, subject, DCTERMS.source, metadata.file_name)
        _add_ref_links(graph, subject, entity.ref_ids, entity_map, instance_ns, _STEP.references)

    if pmi_doc is not None:
        _add_pmi_instances(graph, pmi_doc, instance_ns, entity_map)

    return graph.serialize(format="turtle")


def _add_pmi_instances(graph: Graph, pmi_doc: StepPMIDocument, instance_ns: Namespace, entity_map: Dict[int, StepP21Entity]) -> None:
    def _pmi_subject(kind: str, step_id: int) -> URIRef:
        return instance_ns[f"{kind}_{step_id}"]

    for tol in pmi_doc.geometric_tolerances:
        subject = _pmi_subject("tolerance", tol.id)
        source = _entity_uri(instance_ns, tol.id)
        graph.add((subject, RDF.type, OWL.NamedIndividual))
        graph.add((subject, RDF.type, _PMI.GeometricTolerance))
        graph.add((subject, RDFS.label, Literal(tol.name or f"Tolerance #{tol.id}")))
        graph.add((subject, _STEP.representsStepEntity, source))
        graph.add((subject, _PROV.wasDerivedFrom, source))
        _literal_if_value(graph, subject, _PMI.toleranceType, tol.tolerance_type)
        _literal_if_value(graph, subject, _PMI.magnitude, tol.magnitude, XSD.double)
        _literal_if_value(graph, subject, _PMI.unit, tol.unit or "mm")
        _literal_if_value(graph, subject, RDFS.comment, tol.description)
        _add_ref_links(graph, subject, tol.toleranced_feature_refs, entity_map, instance_ns, _PMI.tolerancedFeature)
        _add_ref_links(graph, subject, tol.datum_system_refs, entity_map, instance_ns, _PMI.datumSystem)

    for datum in pmi_doc.datums:
        subject = _pmi_subject("datum", datum.id)
        source = _entity_uri(instance_ns, datum.id)
        graph.add((subject, RDF.type, OWL.NamedIndividual))
        graph.add((subject, RDF.type, _PMI.Datum))
        graph.add((subject, RDFS.label, Literal(datum.name or datum.label or f"Datum #{datum.id}")))
        graph.add((subject, _STEP.representsStepEntity, source))
        graph.add((subject, _PROV.wasDerivedFrom, source))
        _literal_if_value(graph, subject, _PMI.datumLabel, datum.label)
        _literal_if_value(graph, subject, _STEP.entityType, datum.datum_type)
        _add_ref_links(graph, subject, datum.feature_refs, entity_map, instance_ns, _PMI.datumFeature)

    for dim in pmi_doc.dimensions:
        subject = _pmi_subject("dimension", dim.id)
        source = _entity_uri(instance_ns, dim.id)
        graph.add((subject, RDF.type, OWL.NamedIndividual))
        graph.add((subject, RDF.type, _PMI.Dimension))
        graph.add((subject, RDFS.label, Literal(dim.name or f"Dimension #{dim.id}")))
        graph.add((subject, _STEP.representsStepEntity, source))
        graph.add((subject, _PROV.wasDerivedFrom, source))
        _literal_if_value(graph, subject, _PMI.dimensionType, dim.dimension_type)
        _literal_if_value(graph, subject, _PMI.nominalValue, dim.nominal_value, XSD.double)
        _literal_if_value(graph, subject, _PMI.lowerTolerance, dim.lower_tolerance, XSD.double)
        _literal_if_value(graph, subject, _PMI.upperTolerance, dim.upper_tolerance, XSD.double)
        _literal_if_value(graph, subject, _PMI.unit, dim.unit or "mm")
        _literal_if_value(graph, subject, RDFS.comment, dim.description)
        _add_ref_links(graph, subject, dim.feature_refs, entity_map, instance_ns, _PMI.measuredFeature)

    for ann in pmi_doc.annotations:
        subject = _pmi_subject("annotation", ann.id)
        source = _entity_uri(instance_ns, ann.id)
        graph.add((subject, RDF.type, OWL.NamedIndividual))
        graph.add((subject, RDF.type, _PMI.Annotation))
        graph.add((subject, RDFS.label, Literal(ann.name or f"Annotation #{ann.id}")))
        graph.add((subject, _STEP.representsStepEntity, source))
        graph.add((subject, _PROV.wasDerivedFrom, source))
        _literal_if_value(graph, subject, _PMI.annotationType, ann.annotation_type)
        _literal_if_value(graph, subject, _PMI.textContent, ann.text)
        _add_ref_links(graph, subject, ann.presentation_refs, entity_map, instance_ns, _PMI.presentationReference)
        _add_ref_links(graph, subject, ann.leader_refs, entity_map, instance_ns, _PMI.leaderReference)


def _integrate_domain_models(base_uri: str, prefix: str, schema: Optional[str]) -> str:
    """Integrate with domain models — semantic ingestion from AP242 EXPRESS.

    Locates bom.xsd/DomainModel.xsd and bom.exp/DomainModel.exp. When EXPRESS
    is found it is fully parsed via the local EXPRESS parser and OWL declarations
    declarations are emitted as a Turtle fragment.  When only bom.xsd is found
    a lightweight traceability comment + owl:imports is emitted instead.
    """
    local_mbd3d_path = _BACKEND_DIR / "data" / "MBD3D_BO"

    configured_domain_path = _configured_domain_model_path(local_mbd3d_path)
    repo_root = _BACKEND_DIR.parent
    ap242_domain = describe_ap242_domain_model()
    ap242_bom = describe_ap242_mbd_bom()

    bom_candidates: List[Path] = [
        local_mbd3d_path / "bom.xsd",
        local_mbd3d_path / "DomainModel.xsd",
    ]
    exp_candidates: List[Path] = [
        local_mbd3d_path / "DomainModel.exp",
        local_mbd3d_path / "bom.exp",
    ]

    additional_search_roots: List[Path] = []
    for candidate_root in [
        configured_domain_path,
        configured_domain_path.parent if configured_domain_path.name.lower() in {"bom.xsd", "bom.exp", "domainmodel.xsd", "domainmodel.exp"} else None,
        repo_root,
        repo_root / "data",
        repo_root / "Depo_onto",
        repo_root / "Depo_onto" / "data",
    ]:
        if candidate_root is None:
            continue
        candidate_path = Path(candidate_root)
        if candidate_path not in additional_search_roots:
            additional_search_roots.append(candidate_path)

    # Additional search roots from env-configured path and common repo layouts
    for root in additional_search_roots:
        if not root.exists():
            continue
        bom_candidates.extend([
            root / "bom.xsd",
            root / "DomainModel.xsd",
            root / "data" / "business_object_models" / "managed_model_based_3d_engineering" / "bom.xsd",
            root / "business_object_models" / "managed_model_based_3d_engineering" / "bom.xsd",
            root / "Depo_onto" / "data" / "business_object_models" / "managed_model_based_3d_engineering" / "bom.xsd",
            root / "managed_model_based_3d_engineering_domain" / "Domain_model" / "DomainModel.xsd",
            root / "managed_model_based_3d_engineering_domain" / "Domain_model" / "bom.xsd",
        ])
        exp_candidates.extend([
            root / "bom.exp",
            root / "DomainModel.exp",
            root / "data" / "business_object_models" / "managed_model_based_3d_engineering" / "bom.exp",
            root / "business_object_models" / "managed_model_based_3d_engineering" / "bom.exp",
            root / "Depo_onto" / "data" / "business_object_models" / "managed_model_based_3d_engineering" / "bom.exp",
            root / "managed_model_based_3d_engineering_domain" / "Domain_model" / "DomainModel.exp",
            root / "managed_model_based_3d_engineering_domain" / "Domain_model" / "bom.exp",
        ])

    bom_ref = next((p for p in bom_candidates if p.exists()), None)
    exp_ref = next((p for p in exp_candidates if p.exists()), None)

    if bom_ref is None and exp_ref is None:
        logger.info("No AP242 domain references found (bom.xsd / DomainModel.exp), skipping integration")
        return ""

    # Header comment block
    ttl_parts: List[str] = [
        "\n# ── AP242 Domain Model Integration ────────────────────────────────────",
        f"# Detected STEP schema : {schema}",
    ]
    if bom_ref:
        ttl_parts.append(f"# AP242 exchange schema (XSD) : {bom_ref}")
    else:
        ttl_parts.append(f"# AP242 exchange schema (XSD) : {ap242_domain['xsd_url']}")
        ttl_parts.append(f"# AP242 domain model edition : {ap242_domain['edition']}")
        ttl_parts.append(f"# AP242 XSD version : {ap242_domain['xsd_version']}")
    ttl_parts.append(f"# AP242 MBD BOM schema : {ap242_bom['schema_name']}")
    ttl_parts.append(f"# AP242 MBD BOM namespace : {ap242_bom['namespace']}")
    if exp_ref:
        ttl_parts.append(f"# AP242 semantic authority (EXPRESS) : {exp_ref}")
    ttl_parts.append("")

    # Schema-protocol import assertion
    schema_upper = (schema or "").upper()
    if "AP203" in schema_upper:
        ttl_parts.append(f"<{base_uri}> owl:imports <http://www.step-nc.org/ap203#> .")
    elif "AP214" in schema_upper:
        ttl_parts.append(f"<{base_uri}> owl:imports <http://www.step-nc.org/ap214#> .")
    else:
        # AP242 (or unknown — default to AP242 when domain refs present)
        ttl_parts.append(f"<{base_uri}> owl:imports <http://www.step-nc.org/ap242#> .")
    ttl_parts.append("")

    # ── Semantic ingestion from DomainModel.exp ────────────────────────────
    if exp_ref is not None:
        try:
            try:
                from .express_parser import parse_express, emit_owl_ttl as _emit_express_owl
            except ImportError:
                from express_parser import parse_express, emit_owl_ttl as _emit_express_owl  # type: ignore
            dm_base = "http://IAE-depo.com/ap242dm#"
            express_schema = parse_express(exp_ref)
            owl_fragment = _emit_express_owl(
                express_schema,
                base_uri=dm_base,
                prefix="ap242dm",
                source_path=exp_ref,
            )
            ttl_parts.append(owl_fragment)
            logger.info(
                f"EXPRESS semantic ingestion: {len(express_schema.entities)} entities, "
                f"{len(express_schema.enumerations)} enumerations, "
                f"{len(express_schema.select_types)} select types emitted as OWL"
            )
        except Exception as exc:
            logger.warning(f"EXPRESS ingestion failed ({exp_ref.name}): {exc} — falling back to traceability-only")
            ttl_parts.append(f"# EXPRESS ingestion error: {exc}")
    elif bom_ref is not None:
        ttl_parts.append(f"# Traceability only — EXPRESS schema not found; XSD exchange reference: {bom_ref}")

    return "\n".join(ttl_parts) + "\n"


def copy_ap242_reference_ontology(output_dir: Path) -> Dict[str, Path]:
    """Copy AP242 reference package beside generated STEP TTL files.

    Package mode is controlled via AP242_REFERENCE_PACKAGE env var:
        - lean (default): ap242_ontology.ttl + ap242_shapes.ttl
        - full: adds owl serialization + mbd3d model + alignment artifacts
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    copied: Dict[str, Path] = {}

    ttl_src = _REFERENCE_ONTOLOGY_SRC / "ap242_ontology.ttl"
    if ttl_src.exists():
        ttl_dst = output_dir / "ap242_ontology.ttl"
        shutil.copyfile(ttl_src, ttl_dst)
        copied["ontology_ttl"] = ttl_dst

        if _AP242_PACKAGE_MODE == "full":
            if Graph is None:
                raise RuntimeError(
                    "rdflib is required to serialize AP242 reference ontology to OWL. "
                    "Run backend\\setup.bat --backend or install backend requirements."
                ) from _RDFLIB_IMPORT_ERROR
            graph = Graph()
            graph.parse(str(ttl_dst), format="turtle")
            owl_dst = output_dir / "ap242_ontology.owl"
            graph.serialize(destination=str(owl_dst), format="xml")
            copied["ontology_owl"] = owl_dst

    shapes_src = _REFERENCE_ONTOLOGY_SRC / "ap242_shapes.ttl"
    if shapes_src.exists():
        shapes_dst = output_dir / "ap242_shapes.ttl"
        shutil.copyfile(shapes_src, shapes_dst)
        copied["shapes_ttl"] = shapes_dst

    if _AP242_PACKAGE_MODE == "full":
        # Full schema-derived MBD3D model (generated from bom.xsd)
        mbd3d_ttl_src = _REFERENCE_ONTOLOGY_SRC / "ap242_mbd3d_model.ttl"
        if mbd3d_ttl_src.exists():
            mbd3d_ttl_dst = output_dir / "ap242_mbd3d_model.ttl"
            shutil.copyfile(mbd3d_ttl_src, mbd3d_ttl_dst)
            copied["mbd3d_model_ttl"] = mbd3d_ttl_dst

        mbd3d_owl_src = _REFERENCE_ONTOLOGY_SRC / "ap242_mbd3d_model.owl"
        if mbd3d_owl_src.exists():
            mbd3d_owl_dst = output_dir / "ap242_mbd3d_model.owl"
            shutil.copyfile(mbd3d_owl_src, mbd3d_owl_dst)
            copied["mbd3d_model_owl"] = mbd3d_owl_dst

        alignment_ttl_src = _REFERENCE_ONTOLOGY_SRC / "ap242_mbd3d_alignment.ttl"
        if alignment_ttl_src.exists():
            alignment_ttl_dst = output_dir / "ap242_mbd3d_alignment.ttl"
            shutil.copyfile(alignment_ttl_src, alignment_ttl_dst)
            copied["alignment_ttl"] = alignment_ttl_dst

        alignment_owl_src = _REFERENCE_ONTOLOGY_SRC / "ap242_mbd3d_alignment.owl"
        if alignment_owl_src.exists():
            alignment_owl_dst = output_dir / "ap242_mbd3d_alignment.owl"
            shutil.copyfile(alignment_owl_src, alignment_owl_dst)
            copied["alignment_owl"] = alignment_owl_dst

    return copied


def _count_ttl_classes(ttl_content: str) -> int:
    """Count OWL classes in TTL content."""
    return ttl_content.count('rdfs:subClassOf')


def _count_ttl_properties(ttl_content: str) -> int:
    """Count OWL properties in TTL content."""
    return ttl_content.count('owl:DatatypeProperty') + ttl_content.count('owl:ObjectProperty')


def _count_ttl_individuals(ttl_content: str) -> int:
    """Count OWL individuals in TTL content."""
    return ttl_content.count('owl:NamedIndividual')

