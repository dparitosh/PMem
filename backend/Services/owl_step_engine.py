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

try:
    from rdflib import Graph, URIRef
    _RDFLIB_IMPORT_ERROR = None
except ModuleNotFoundError as exc:
    Graph = None  # type: ignore[assignment]
    URIRef = str  # type: ignore[assignment]
    _RDFLIB_IMPORT_ERROR = exc

try:
    from .ap242_domain_model import describe_ap242_domain_model, describe_ap242_mbd_bom
except ImportError:
    from ap242_domain_model import describe_ap242_domain_model, describe_ap242_mbd_bom  # type: ignore

# Paths adjusted for backend Services layout
_BACKEND_DIR = Path(__file__).resolve().parent.parent
_DEFAULT_STP_OUTPUT = _BACKEND_DIR / "output" / "stp"
_REFERENCE_ONTOLOGY_SRC = _BACKEND_DIR / "ontologies" / "generated"
_AP242_ONTO_URI = URIRef("http://IAE-depo.com/ap242-ontology")
_AP242_PACKAGE_MODE = os.getenv("AP242_REFERENCE_PACKAGE", "full").strip().lower()


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
        
        # Initialize TTL content
        ttl_content = _generate_ttl_header(base_uri, namespace_prefix, metadata)
        
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
        
        if include_pmi:
            # Use enhanced PMI parser for comprehensive extraction
            logger.info("Extracting PMI data using enhanced parser...")
            pmi_doc = parse_step_with_pmi(file_path)
            ttl_content += _convert_basic_entities_to_ttl(pmi_doc.entities, base_uri, namespace_prefix)
            ttl_content += _convert_pmi_to_ttl(pmi_doc, base_uri, namespace_prefix)
            
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
            ttl_content += _convert_basic_entities_to_ttl(entities, base_uri, namespace_prefix)
            stats["entities_processed"] = len(entities)
        
        # Add entity mappings and relationships
        ttl_content += _generate_step_ontology_classes(base_uri, namespace_prefix)
        
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


def _generate_ttl_header(base_uri: str, prefix: str, metadata: StepFileMeta) -> str:
    """Generate TTL file header with ontology declarations."""
    schema_line = f'    step:fileSchema "{metadata.file_schema}" ;\n' if metadata.file_schema else ""
    namespace_line = f'    step:schemaNamespace "{metadata.namespace}" ;\n' if metadata.namespace else ""
    schema_location_line = f'    step:schemaLocation "{metadata.schema_location}" ;\n' if metadata.schema_location else ""
    schema_version_line = f'    step:schemaVersion "{metadata.schema_version}" ;\n' if metadata.schema_version else ""
    header = f"""@prefix {prefix}: <{base_uri}> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix pmi: <http://example.org/pmi#> .
@prefix step: <http://www.step-nc.org/step#> .

<{base_uri}> a owl:Ontology ;
    rdfs:label "STEP File Ontology" ;
    rdfs:comment "Generated from STEP file: {metadata.file_name}" ;
    owl:imports <{_AP242_ONTO_URI}> ;
    owl:versionInfo "1.0" ;
{schema_line}
{namespace_line}
{schema_location_line}
{schema_version_line}
    step:sourceFormat "{metadata.format}" .

"""
    return header


def _convert_pmi_to_ttl(pmi_doc: StepPMIDocument, base_uri: str, prefix: str) -> str:
    """Convert PMI document to TTL format."""
    ttl = "\n# PMI (Product Manufacturing Information) Data\n\n"
    
    # Convert geometric tolerances
    for tol in pmi_doc.geometric_tolerances:
        tol_uri = f"{base_uri}tolerance_{tol.id}"
        ttl += f"""<{tol_uri}> a pmi:GeometricTolerance ;
    rdfs:label "{tol.name or f'Tolerance_{tol.id}'}" ;
    pmi:toleranceType "{tol.tolerance_type}" ;
    pmi:magnitude {tol.magnitude or 0.0} ;
    pmi:unit "{tol.unit or 'mm'}" ;
    pmi:description "{tol.description or ''}" .

"""
    
    # Convert datums
    for datum in pmi_doc.datums:
        datum_uri = f"{base_uri}datum_{datum.id}"
        ttl += f"""<{datum_uri}> a pmi:Datum ;
    rdfs:label "{datum.name or f'Datum_{datum.id}'}" ;
    pmi:datumLabel "{datum.label or ''}" ;
    pmi:datumType "{datum.datum_type or 'UNKNOWN'}" .

"""
    
    # Convert dimensions
    for dim in pmi_doc.dimensions:
        dim_uri = f"{base_uri}dimension_{dim.id}"
        ttl += f"""<{dim_uri}> a pmi:Dimension ;
    rdfs:label "{dim.name or f'Dimension_{dim.id}'}" ;
    pmi:dimensionType "{dim.dimension_type}" ;
    pmi:nominalValue {dim.nominal_value or 0.0} ;
    pmi:unit "{dim.unit or 'mm'}" .

"""
    
    # Convert annotations
    for ann in pmi_doc.annotations:
        ann_uri = f"{base_uri}annotation_{ann.id}"
        ttl += f"""<{ann_uri}> a pmi:Annotation ;
    rdfs:label "{ann.name or f'Annotation_{ann.id}'}" ;
    pmi:annotationType "{ann.annotation_type}" ;
    pmi:textContent "{ann.text or ''}" .

"""
    
    return ttl


def _convert_basic_entities_to_ttl(entities: List, base_uri: str, prefix: str) -> str:
    """Convert basic STEP entities to TTL format."""
    ttl = "\n# Basic STEP Entities\n\n"
    
    for entity in entities:
        entity_uri = f"{base_uri}entity_{entity.step_id}"
        ttl += f"""<{entity_uri}> a step:{entity.entity_type} ;
    step:stepId {entity.step_id} ;
    step:entityType "{entity.entity_type}" ;
    step:rawArgs "{_escape_ttl_string(entity.raw_args[:200])}" .

"""
    
    return ttl


def _generate_step_ontology_classes(base_uri: str, prefix: str) -> str:
    """Generate STEP ontology class definitions."""
    return f"""
# STEP Ontology Classes
pmi:GeometricTolerance rdfs:subClassOf owl:Thing ;
    rdfs:label "Geometric Tolerance" ;
    rdfs:comment "GD&T geometric tolerance specification" .

pmi:Datum rdfs:subClassOf owl:Thing ;
    rdfs:label "Datum" ;
    rdfs:comment "Datum reference for geometric tolerances" .

pmi:Dimension rdfs:subClassOf owl:Thing ;
    rdfs:label "Dimension" ;
    rdfs:comment "Dimensional constraint or measurement" .

pmi:Annotation rdfs:subClassOf owl:Thing ;
    rdfs:label "Annotation" ;
    rdfs:comment "Text annotation or note" .

step:Entity rdfs:subClassOf owl:Thing ;
    rdfs:label "STEP Entity" ;
    rdfs:comment "Generic STEP file entity" .

# Properties
pmi:toleranceType a owl:DatatypeProperty ;
    rdfs:domain pmi:GeometricTolerance ;
    rdfs:range xsd:string .

pmi:magnitude a owl:DatatypeProperty ;
    rdfs:domain pmi:GeometricTolerance ;
    rdfs:range xsd:double .

step:stepId a owl:DatatypeProperty ;
    rdfs:domain step:Entity ;
    rdfs:range xsd:integer .

step:entityType a owl:DatatypeProperty ;
    rdfs:domain step:Entity ;
    rdfs:range xsd:string .

"""


def _integrate_domain_models(base_uri: str, prefix: str, schema: Optional[str]) -> str:
    """Integrate with domain models — semantic ingestion from AP242 EXPRESS.

    Locates bom.xsd/DomainModel.xsd and bom.exp/DomainModel.exp. When EXPRESS
    is found it is fully parsed via the local EXPRESS parser and OWL declarations
    declarations are emitted as a Turtle fragment.  When only bom.xsd is found
    a lightweight traceability comment + owl:imports is emitted instead.
    """
    local_mbd3d_path = _BACKEND_DIR / "data" / "MBD3D_BO"

    configured_domain_path = _configured_domain_model_path(local_mbd3d_path)
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

    # Additional search roots from the env-configured domain path
    for root in [configured_domain_path]:
        if not root.exists():
            continue
        bom_candidates.extend([
            root / "bom.xsd",
            root / "DomainModel.xsd",
            root / "data" / "business_object_models" / "managed_model_based_3d_engineering" / "bom.xsd",
            root / "business_object_models" / "managed_model_based_3d_engineering" / "bom.xsd",
            root / "managed_model_based_3d_engineering_domain" / "Domain_model" / "DomainModel.xsd",
            root / "managed_model_based_3d_engineering_domain" / "Domain_model" / "bom.xsd",
        ])
        exp_candidates.extend([
            root / "bom.exp",
            root / "DomainModel.exp",
            root / "data" / "business_object_models" / "managed_model_based_3d_engineering" / "bom.exp",
            root / "business_object_models" / "managed_model_based_3d_engineering" / "bom.exp",
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


def _escape_ttl_string(s: str) -> str:
    """Escape string for TTL format."""
    return s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r')


def _count_ttl_classes(ttl_content: str) -> int:
    """Count OWL classes in TTL content."""
    return ttl_content.count('rdfs:subClassOf')


def _count_ttl_properties(ttl_content: str) -> int:
    """Count OWL properties in TTL content."""
    return ttl_content.count('owl:DatatypeProperty') + ttl_content.count('owl:ObjectProperty')


def _count_ttl_individuals(ttl_content: str) -> int:
    """Count OWL individuals in TTL content."""
    return ttl_content.count(' a pmi:') + ttl_content.count(' a step:')
