"""
Generic XSD → OWL2/Turtle Converter
=====================================
Converts any collection of XML Schema (XSD) files into an OWL2 ontology
in Turtle format.  All domain-specific details (base URI, ontology title,
SKOS categories, which files to process) live in an OntologyConfig object —
nothing is hardcoded in the converter logic.

Supported datasource types:
  • XSD files        — primary path (B2MML, IPC-2581, AP242, PLCS, …)
  • JSON config      — load OntologyConfig from a .json file
  • Environment vars — minimal headless / CI-CD mode

Built-in configs (ready to use):
  b2mml_config()   — ISA-95 / B2MML-V0600 TechTransfer ontology
  minimal_config() — bare-minimum template for a new standard

Usage:
    # B2MML default
    python convert_b2mml_to_ttl.py

    # Explicit paths (B2MML default config)
    python convert_b2mml_to_ttl.py <schema_dir> <output.ttl>

    # External JSON config (any standard)
    python convert_b2mml_to_ttl.py --config my_standard.json

    # Environment-variable driven (all ONTO_* vars)
    python convert_b2mml_to_ttl.py --env

JSON config example (all fields optional; defaults shown):
    {
        "base_uri":        "http://example.org/mystandard#",
        "prefix":          "myns",
        "title":           "My Standard Ontology",
        "description":     "Generated from XSD files",
        "schema_dir":      "C:/schemas/mystandard",
        "target_files":    [],
        "output_ttl":      "MyStandard.ttl"
    }

Environment variables (all ONTO_* prefix):
    ONTO_BASE_URI, ONTO_PREFIX, ONTO_TITLE, ONTO_DESCRIPTION,
    ONTO_CREATOR, ONTO_SOURCE_NS, ONTO_SOURCE_STANDARD,
    ONTO_VERSION, ONTO_SUBJECT, ONTO_SCHEMA_DIR, ONTO_OUTPUT_TTL
"""

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.namespace import DC, DCTERMS, OWL, RDF, RDFS, SKOS, XSD
try:
    from .ontology_utils import safe_fragment
except ImportError:
    from ontology_utils import safe_fragment  # type: ignore

# Industry 4.0 SHACL Support
SH = Namespace("http://www.w3.org/ns/shacl#")
OSLC = Namespace("http://open-services.net/ns/core#")
PROV = Namespace("http://www.w3.org/ns/prov#")

# XSD namespace prefix for XML parsing
XSD_PRE = "{http://www.w3.org/2001/XMLSchema}"

# XSD primitive type → rdflib XSD datatype
XSD_TYPE_MAP = {
    "string":           XSD.string,
    "normalizedString": XSD.normalizedString,
    "boolean":          XSD.boolean,
    "decimal":          XSD.decimal,
    "float":            XSD.float,
    "double":           XSD.double,
    "integer":          XSD.integer,
    "int":              XSD.int,
    "long":             XSD.long,
    "dateTime":         XSD.dateTime,
    "date":             XSD.date,
    "time":             XSD.time,
    "duration":         XSD.duration,
    "anyURI":           XSD.anyURI,
    "base64Binary":     XSD.base64Binary,
    "language":         XSD.language,
    "token":            XSD.token,
}


# ── OntologyConfig ────────────────────────────────────────────────────────────

@dataclass
class OntologyConfig:
    """
    All configuration for one ontology conversion run.
    Replaces every hardcoded constant — pass a different instance to convert
    any XSD-based standard without touching the converter code.
    """

    # ── Identity ──────────────────────────────────────────────────────────────
    base_uri:         str   # Ontology base URI, MUST end with # or /
    prefix:           str   # Turtle namespace prefix
    title:            str   # rdfs:label on owl:Ontology
    description:      str   # rdfs:comment on owl:Ontology

    # ── Provenance (all optional) ─────────────────────────────────────────────
    creator:          str  = "IAE — Industrial Autonomy and Engineering"
    source_ns:        str  = ""   # Original schema namespace (info only)
    source_standard:  str  = ""   # e.g. "ANSI/ISA-95.00.02-2010"
    version_info:     str  = ""
    subject_keywords: str  = ""   # dc:subject
    license_uri:      str  = "http://www.apache.org/licenses/LICENSE-2.0"

    # ── SKOS taxonomy ─────────────────────────────────────────────────────────
    # {category_key: (label, definition)}
    categories:       dict = field(default_factory=dict)
    # {class_name_prefix: category_key}  — longest prefix wins
    category_map:     dict = field(default_factory=dict)
    # Category keys whose SKOS broader should point to the first category key.
    # Leave empty to skip hierarchy wiring.
    category_hierarchy: list = field(default_factory=list)

    # ── Cross-standard bridge pairs (optional) ────────────────────────────────
    # [(source_type_name, bridge_concept_name, comment), ...]
    bridge_pairs:     list = field(default_factory=list)

    # ── XSD source ────────────────────────────────────────────────────────────
    schema_dir:       str  = ""
    # Base file names (no path, no timestamp, no .xsd).
    # Empty list → auto-discover ALL *.xsd files in schema_dir.
    target_files:     list = field(default_factory=list)
    # Ordered preference for timestamp suffixes embedded in file names.
    timestamp_preference: list = field(
        default_factory=lambda: ["2023_02_07", "2023_01_29", "2022_04_16"])

    # ── Output ────────────────────────────────────────────────────────────────
    output_ttl:       str  = ""
    output_owl:       str  = ""   # RDF/XML (.owl) — derived from output_ttl if empty

    # ── Derived helpers ───────────────────────────────────────────────────────

    @property
    def ns(self) -> Namespace:
        return Namespace(self.base_uri)

    def class_uri(self, name: str) -> URIRef:
        return self.ns[_safe_uri_name(name)]

    def prop_uri(self, domain: str, prop_name: str) -> URIRef:
        canonical = self.canonical_property_key(prop_name)
        if canonical is not None:
            return self.ns[f"prop_{canonical}"]
        return self.ns[f"{_safe_uri_name(domain)}_{_safe_uri_name(prop_name)}"]

    def canonical_property_key(self, prop_name: str) -> str | None:
        """Return a canonical key for broadly shared properties, else None."""
        raw = str(prop_name or "").strip()
        if not raw:
            return None
        if ":" in raw:
            pref, local = raw.split(":", 1)
            if pref and local:
                return f"ns_{_safe_uri_name(pref)}_{_safe_uri_name(local)}"

        common = {
            "id", "name", "version", "comment", "description", "signature",
            "contact", "authorizer", "docid", "manufacturerid", "symbolid",
        }
        token = _safe_uri_name(raw).lower()
        if token in common:
            return f"common_{token}"
        return None

    def is_shared_property(self, prop_name: str) -> bool:
        return self.canonical_property_key(prop_name) is not None

    def category_for(self, name: str) -> str:
        """Return category key for a class name using longest prefix match."""
        best_stem, best_cat = "", list(self.categories.keys())[-1] if self.categories else "General"
        for stem, cat in self.category_map.items():
            if name.startswith(stem) and len(stem) > len(best_stem):
                best_stem, best_cat = stem, cat
        return best_cat

    # ── Factory: load from JSON file ──────────────────────────────────────────

    @classmethod
    def from_json(cls, path: str) -> "OntologyConfig":
        """Load config from a JSON file.  Only declared fields are consumed."""
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        valid = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in valid})

    # ── Factory: load from environment variables ──────────────────────────────

    @classmethod
    def from_env(cls) -> "OntologyConfig":
        """Minimal headless config from ONTO_* environment variables."""
        return cls(
            base_uri         = os.getenv("ONTO_BASE_URI",        "http://example.org/ontology#"),
            prefix           = os.getenv("ONTO_PREFIX",          "onto"),
            title            = os.getenv("ONTO_TITLE",           "Generated Ontology"),
            description      = os.getenv("ONTO_DESCRIPTION",     "Auto-generated from XSD source"),
            creator          = os.getenv("ONTO_CREATOR",         "IAE — Industrial Autonomy and Engineering"),
            source_ns        = os.getenv("ONTO_SOURCE_NS",       ""),
            source_standard  = os.getenv("ONTO_SOURCE_STANDARD", ""),
            version_info     = os.getenv("ONTO_VERSION",         ""),
            subject_keywords = os.getenv("ONTO_SUBJECT",         ""),
            schema_dir       = os.getenv("ONTO_SCHEMA_DIR",      ""),
            output_ttl       = os.getenv("ONTO_OUTPUT_TTL",      ""),
            output_owl       = os.getenv("ONTO_OUTPUT_OWL",      ""),
        )


# ── Built-in configs ──────────────────────────────────────────────────────────

def b2mml_config(schema_dir: str = "", output_ttl: str = "") -> OntologyConfig:
    """Ready-to-use config for ISA-95 / B2MML-V0600 TechTransfer ontology."""
    return OntologyConfig(
        base_uri         = "http://IAE-depo.com/b2mml#",
        prefix           = "b2mml",
        title            = "TechTransfer — Unified PLM and MES Ontology",
        description      = (
            "Unified knowledge graph ontology bridging Product Lifecycle Management (PLM) "
            "and Manufacturing Execution Systems (MES) based on ANSI/ISA-95 and B2MML V0600. "
            "Generated from B2MML-BatchML-V0600 XML Schema files."
        ),
        creator          = "IAE — Industrial Autonomy and Engineering",
        source_ns        = "http://www.mesa.org/xml/B2MML-V0600",
        source_standard  = "ANSI/ISA-95.00.02-2010",
        version_info     = "B2MML-V0600",
        subject_keywords = "ISA-95, B2MML, PLM, MES, TechTransfer, Manufacturing",
        categories       = {
            "PLM_ProductDef": ("PLM Product Definition",
                               "Product structure, BOM, work masters from PLM (ISA-95 Part 2)"),
            "MES_Resource":   ("MES Resource Management",
                               "Equipment, personnel, material, physical assets (ISA-95 Part 2)"),
            "MES_Operations": ("MES Operations Management",
                               "Operations definition, scheduling, performance (ISA-95 Part 3/4)"),
            "MES_Production": ("MES Production Management",
                               "Production requests, schedules, performance (ISA-95 Part 2)"),
            "MES_Work":       ("MES Work Management",
                               "Work capabilities, definitions, schedules (ISA-95 Part 4)"),
            "MES_Process":    ("MES Process Segments",
                               "Process and resource relationship networks (ISA-95 Part 2)"),
            "ISA88_Batch":    ("ISA-88 Batch Management",
                               "Batch information, general recipe, batch production records"),
            "Common":         ("Common Data Types",
                               "Shared types: identifiers, hierarchy scope, properties, parameters"),
        },
        category_map     = {
            # MES Resources
            "Equipment":         "MES_Resource",
            "EquipmentClass":    "MES_Resource",
            "PhysicalAsset":     "MES_Resource",
            "PhysicalAssetClass":"MES_Resource",
            "Personnel":         "MES_Resource",
            "PersonnelClass":    "MES_Resource",
            "Person":            "MES_Resource",
            "MaterialClass":     "MES_Resource",
            "MaterialDefinition":"MES_Resource",
            "MaterialLot":       "MES_Resource",
            "MaterialSubLot":    "MES_Resource",
            # PLM / Product
            "ProductDefinition": "PLM_ProductDef",
            "ProductSegment":    "PLM_ProductDef",
            "BillOfMaterials":   "PLM_ProductDef",
            "WorkMaster":        "PLM_ProductDef",
            "WorkDirective":     "PLM_ProductDef",
            # Operations / MES Execution
            "OperationsDefinition":  "MES_Operations",
            "OperationsSegment":     "MES_Operations",
            "OperationsSchedule":    "MES_Operations",
            "OperationsRequest":     "MES_Operations",
            "OperationsPerformance": "MES_Operations",
            "OperationsResponse":    "MES_Operations",
            "OperationsCapability":  "MES_Operations",
            # Production
            "ProductionSchedule":    "MES_Production",
            "ProductionRequest":     "MES_Production",
            "ProductionPerformance": "MES_Production",
            "ProductionCapability":  "MES_Production",
            # Work (ISA-95 Part 4)
            "WorkCapability":        "MES_Work",
            "WorkDefinition":        "MES_Work",
            "WorkSchedule":          "MES_Work",
            "WorkPerformance":       "MES_Work",
            "WorkAlert":             "MES_Work",
            "WorkflowSpecification": "MES_Work",
            # Batch (ISA-88)
            "BatchInformation":      "ISA88_Batch",
            "GeneralRecipe":         "ISA88_Batch",
            "BatchProductionRecord": "ISA88_Batch",
            # Process
            "ProcessSegment":              "MES_Process",
            "ResourceRelationshipNetwork": "MES_Process",
            # Common
            "HierarchyScope": "Common",
            "Property":       "Common",
            "Parameter":      "Common",
        },
        category_hierarchy = [
            "MES_Resource", "MES_Production", "MES_Work", "MES_Process", "ISA88_Batch",
        ],
        bridge_pairs     = [
            ("ProductDefinitionType",    "PLM_ProductDefinition",
             "Product definition shared between PLM BOM and MES product segment"),
            ("OperationsDefinitionType", "PLM_ManufacturingProcess",
             "Operations definition maps to PLM manufacturing process"),
            ("WorkMasterType",           "PLM_WorkInstruction",
             "Work master corresponds to PLM work instruction / routing"),
            ("MaterialDefinitionType",   "PLM_PartDefinition",
             "Material definition aligns with PLM part definition"),
            ("EquipmentType",            "PLM_ToolingAsset",
             "Equipment corresponds to PLM tooling/fixture asset"),
            ("ProductionScheduleType",   "MES_ProductionOrder",
             "Production schedule contains MES production orders"),
            ("OperationsPerformanceType","MES_ActualProductionRecord",
             "Operations performance is the MES as-built / actual production record"),
            ("BatchProductionRecordType","ISA88_BatchRecord",
             "Batch production record (ISA-88) traces actual batch execution"),
        ],
        target_files     = [
            "B2MML-V0600-Common",
            "B2MML-V0600-Equipment",
            "B2MML-V0600-Material",
            "B2MML-V0600-Personnel",
            "B2MML-V0600-PhysicalAsset",
            "B2MML-V0600-ProcessSegment",
            "B2MML-V0600-ProductDefinition",
            "B2MML-V0600-ProductionSchedule",
            "B2MML-V0600-ProductionPerformance",
            "B2MML-V0600-ProductionCapability",
            "B2MML-V0600-OperationsDefinition",
            "B2MML-V0600-OperationsSchedule",
            "B2MML-V0600-OperationsPerformance",
            "B2MML-V0600-OperationsCapability",
            "B2MML-V0600-WorkDefinition",
            "B2MML-V0600-WorkSchedule",
            "B2MML-V0600-WorkPerformance",
            "B2MML-V0600-WorkCapability",
            "B2MML-V0600-WorkAlert",
            "B2MML-V0600-WorkflowSpecification",
            "B2MML-V0600-ResourceRelationshipNetwork",
            "BatchML-V0600-BatchInformation",
            "BatchML-V0600-GeneralRecipe",
            "BatchML-V0600-BatchProductionRecord",
        ],
        schema_dir       = schema_dir or os.getenv("ONTO_SCHEMA_DIR", ""),
        output_ttl       = output_ttl or os.getenv("ONTO_OUTPUT_TTL") or (
            str(Path(__file__).resolve().parent.parent / "ontologies" / "generated" / "B2MML_TechTransfer.ttl")
        ),
        output_owl       = os.getenv("ONTO_OUTPUT_OWL") or (
            str(Path(__file__).resolve().parent.parent / "ontologies" / "generated" / "B2MML_TechTransfer.owl")
        ),
    )


def minimal_config(base_uri: str, prefix: str, title: str,
                   schema_dir: str, output_ttl: str) -> OntologyConfig:
    """
    Bare-minimum template — no categories, no bridge pairs.
    Pass this to convert_xsd_to_owl() for a new standard without any
    domain-specific taxonomy.  Extend afterwards by setting .categories,
    .category_map, .bridge_pairs.
    """
    return OntologyConfig(
        base_uri   = base_uri,
        prefix     = prefix,
        title      = title,
        description= f"OWL2 ontology generated from XSD files in {schema_dir}",
        schema_dir = schema_dir,
        output_ttl = output_ttl,
    )


# ── Utility functions (pure, no config dependency) ───────────────────────────

def _local(name: str) -> str:
    """Strip namespace prefix from a qualified XSD type name."""
    return name.split(":", 1)[1] if ":" in name else name


def _safe_uri_name(name: str) -> str:
    """Convert a type name to a safe URI-compatible local name."""
    return safe_fragment(name)


def _extract_annotation(element) -> "str | None":
    """
    Extract xs:annotation > xs:documentation text from an XSD element.
    Returns the text content of the first xs:documentation found, or None.
    """
    annotation = element.find(f"{XSD_PRE}annotation")
    if annotation is not None:
        documentation = annotation.find(f"{XSD_PRE}documentation")
        if documentation is not None and documentation.text:
            return documentation.text.strip()
    return None


def _collect_simple_types(xsd_paths: list) -> dict:
    """
    Pass 1 — scan every XSD file and return a mapping:
        type_local_name  →  rdflib XSD datatype URIRef
    for every type that ultimately resolves to an XSD primitive via:
      • xs:simpleType  > xs:restriction base="xs:..."
      • xs:complexType > xs:simpleContent > xs:extension/restriction base="xs:..."
    Chains are resolved recursively (e.g. QuantityType → NumericType → xs:decimal).
    Works unchanged for B2MML, IPC-2581, AP242, or any other XSD standard.
    """
    # raw[name] = immediate base name (may itself be a user-defined type)
    raw: dict = {}

    for path in xsd_paths:
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError:
            continue

        # xs:simpleType with xs:restriction — top-level only
        for st in root.findall(f"{XSD_PRE}simpleType"):
            name = st.get("name", "")
            if not name:
                continue
            restr = st.find(f"{XSD_PRE}restriction")
            if restr is not None:
                base = _local(restr.get("base", ""))
                if base:
                    raw[name] = base

        # xs:complexType with xs:simpleContent — top-level only

        for ct in root.findall(f"{XSD_PRE}complexType"):
            name = ct.get("name", "")
            if not name:
                continue
            sc = ct.find(f"{XSD_PRE}simpleContent")
            if sc is None:
                continue
            for tag in (f"{XSD_PRE}extension", f"{XSD_PRE}restriction"):
                elem = sc.find(tag)
                if elem is not None:
                    base = _local(elem.get("base", ""))
                    if base:
                        raw[name] = base
                    break

    # Resolve chains to an XSD primitive, e.g.:
    #   QuantityValueType → NumericType → decimal  →  XSD.decimal
    resolved: dict = {}

    def _resolve(name: str, visited: set):
        if name in resolved:
            return resolved[name]
        if name in XSD_TYPE_MAP:
            return XSD_TYPE_MAP[name]
        if name in visited or name not in raw:
            return None
        visited.add(name)
        result = _resolve(raw[name], visited)
        if result:
            resolved[name] = result
        return result



    for name in list(raw):
        _resolve(name, set())

    return resolved


def build_ontology_header(g: Graph, cfg: OntologyConfig) -> None:
    """Write the owl:Ontology node with full metadata from cfg."""
    from datetime import datetime
    
    onto = URIRef(cfg.base_uri)
    g.add((onto, RDF.type,        OWL.Ontology))
    g.add((onto, RDFS.label,      Literal(cfg.title)))
    g.add((onto, RDFS.comment,    Literal(cfg.description)))
    g.add((onto, DC.title,        Literal(cfg.title)))
    g.add((onto, DC.creator,      Literal(cfg.creator)))
    
    # Enhanced metadata for semantic correctness
    g.add((onto, DCTERMS.created, Literal(datetime.now().isoformat(), datatype=XSD.dateTime)))
    g.add((onto, DCTERMS.modified, Literal(datetime.now().isoformat(), datatype=XSD.dateTime)))
    g.add((onto, OWL.versionIRI, URIRef(f"{cfg.base_uri}v{cfg.version_info or '1.0'}")))
    
    if cfg.subject_keywords:
        g.add((onto, DC.subject,  Literal(cfg.subject_keywords)))
    if cfg.source_ns:
        g.add((onto, DCTERMS.source,  Literal(cfg.source_ns)))
    if cfg.license_uri:
        g.add((onto, DCTERMS.license, URIRef(cfg.license_uri)))
    if cfg.version_info:
        g.add((onto, OWL.versionInfo, Literal(cfg.version_info)))
    if cfg.source_standard:
        g.add((onto, DCTERMS.conformsTo, Literal(cfg.source_standard)))
        g.add((onto, RDFS.comment,    Literal(f"Standard: {cfg.source_standard}")))
    
    # Essential OWL2 imports for semantic completeness
    g.add((onto, OWL.imports, URIRef("http://www.w3.org/2004/02/skos/core")))
    g.add((onto, OWL.imports, URIRef("http://www.w3.org/ns/shacl")))
    g.add((onto, OWL.imports, URIRef("http://purl.org/dc/terms/")))
    g.add((onto, OWL.imports, URIRef("http://open-services.net/ns/core")))
    
    # **CRITICAL: Declare SKOS.Concept as OWL.Class for semantic clarity**
    # This establishes the foundation for all SKOS concept definitions
    g.add((SKOS.Concept, RDF.type, OWL.Class))
    g.add((SKOS.Concept, RDFS.label, Literal("SKOS Concept")))
    g.add((SKOS.Concept, RDFS.comment, Literal(
        f"SKOS concept class representing controlled vocabulary terms in {cfg.title}")))
    g.add((SKOS.Concept, RDFS.isDefinedBy,
           URIRef("http://www.w3.org/2004/02/skos/core#Concept")))
    g.add((onto, OWL.imports, URIRef("http://open-services.net/ns/core")))


def build_skos_categories(g: Graph, cfg: OntologyConfig) -> None:
    """Create SKOS ConceptScheme + Concept nodes from cfg.categories."""
    if not cfg.categories:
        return

    scheme_key = _safe_uri_name(cfg.prefix) + "Scheme"
    scheme = cfg.ns[scheme_key]
    g.add((scheme, RDF.type,        SKOS.ConceptScheme))
    g.add((scheme, RDFS.label,      Literal(f"{cfg.title} — Concept Scheme")))
    g.add((scheme, SKOS.definition, Literal(
        f"Organises {cfg.title} classes into functional categories."
    )))

    keys = list(cfg.categories.keys())
    root_key = keys[0] if keys else None

    for cat_key, (cat_label, cat_def) in cfg.categories.items():
        cat_uri = cfg.ns[cat_key]
        g.add((cat_uri, RDF.type,        SKOS.Concept))
        g.add((cat_uri, SKOS.prefLabel,  Literal(cat_label, lang="en")))
        g.add((cat_uri, SKOS.definition, Literal(cat_def, lang="en")))
        g.add((cat_uri, SKOS.inScheme,   scheme))
        g.add((cat_uri, RDFS.label,      Literal(cat_label)))
        g.add((cat_uri, RDFS.comment,    Literal(cat_def)))

    if root_key and root_key in cfg.categories:
        root_uri = cfg.ns[root_key]
        g.add((scheme, SKOS.hasTopConcept, root_uri))
        g.add((root_uri, SKOS.topConceptOf, scheme))

    # Wire configured hierarchy — all listed categories point broader → root_key
    if root_key:
        for cat_key in cfg.category_hierarchy:
            if cat_key in cfg.categories and cat_key != root_key:
                g.add((cfg.ns[cat_key], SKOS.broader,    cfg.ns[root_key]))


def _get_oslc_occurs(min_occurs: str, max_occurs: str) -> URIRef:
    """Map XSD minOccurs/maxOccurs to OSLC occurs."""
    if min_occurs == "1" and max_occurs == "1":
        return OSLC["Exactly-one"]
    elif min_occurs == "0" and max_occurs == "1":
        return OSLC["Zero-or-one"]
    elif min_occurs == "0" and max_occurs == "unbounded":
        return OSLC["Zero-or-many"]
    elif min_occurs == "1" and max_occurs == "unbounded":
        return OSLC["One-or-many"]
    else:
        # Default fallback
        return OSLC["Zero-or-many"]


def _extract_inline_simple_base(element) -> str:
    """Extract primitive/wrapper base from inline simpleType restrictions/extensions."""
    simple_type = element.find(f"{XSD_PRE}simpleType")
    if simple_type is not None:
        restriction = simple_type.find(f"{XSD_PRE}restriction")
        if restriction is not None:
            return _local(restriction.get("base", ""))

    simple_content = element.find(f"{XSD_PRE}simpleContent")
    if simple_content is not None:
        restriction = simple_content.find(f"{XSD_PRE}restriction")
        extension = simple_content.find(f"{XSD_PRE}extension")
        base_elem = restriction if restriction is not None else extension
        if base_elem is not None:
            return _local(base_elem.get("base", ""))

    return ""


def _ensure_class_stub(g: Graph, cfg: OntologyConfig, type_local: str, source_tag: str) -> URIRef:
    """Ensure a referenced type exists as an owl:Class in the generated graph."""
    class_uri = cfg.class_uri(type_local)
    if (class_uri, RDF.type, OWL.Class) not in g:
        g.add((class_uri, RDF.type, OWL.Class))
        g.add((class_uri, RDFS.label, Literal(type_local)))
        g.add((class_uri, RDFS.comment, Literal(
            f"Auto-generated class stub for referenced type '{type_local}'."
        )))
        if cfg.categories:
            g.add((class_uri, DCTERMS.subject, cfg.ns[cfg.category_for(type_local)]))
        g.add((class_uri, DC.source, Literal(source_tag)))
    return class_uri


def _ensure_owl_thing_metadata(g: Graph, source_tag: str) -> None:
    """Ensure owl:Thing satisfies local SHACL class metadata expectations."""
    g.add((OWL.Thing, RDF.type, OWL.Class))
    g.add((OWL.Thing, RDFS.label, Literal("Thing")))
    g.add((OWL.Thing, RDFS.comment, Literal(
        "Fallback class used when XSD object-property target type is unresolved."
    )))
    g.add((OWL.Thing, DC.source, Literal(source_tag)))

def parse_complex_type(g: Graph, ct_element, file_stem: str,
                       seen_classes: set, cfg: OntologyConfig,
                       simple_types: dict, prop_kinds: dict,
                       strict_semantics: bool = True) -> None:
    """Map one xsd:complexType → owl:Class with its child elements as properties.

    simple_types — output of _collect_simple_types(); maps type name → XSD datatype.
    Any property whose range resolves to an XSD primitive via simple_types is
    classified as owl:DatatypeProperty; all others become owl:ObjectProperty.
    This logic is fully generic and works for any XSD standard.
    """
    type_name = ct_element.get("name", "")
    if not type_name:
        return

    class_uri = cfg.class_uri(type_name)
    if class_uri in seen_classes:
        return
    seen_classes.add(class_uri)

    cat = cfg.category_for(type_name)
    source_tag = f"{cfg.source_standard or cfg.prefix} / {file_stem}"

    g.add((class_uri, RDF.type,      OWL.Class))
    g.add((class_uri, RDF.type,      OSLC.ResourceShape))
    g.add((class_uri, OSLC.describes, class_uri))
    g.add((class_uri, RDFS.label,    Literal(type_name)))

    annotation_text = _extract_annotation(ct_element)
    if annotation_text:
        g.add((class_uri, RDFS.comment,    Literal(annotation_text)))
        g.add((class_uri, SKOS.definition, Literal(annotation_text)))
    else:
        g.add((class_uri, RDFS.comment,  Literal(
            f"Class from {file_stem}. Source complexType '{type_name}'."
        )))

    if cfg.categories:
        g.add((class_uri, DCTERMS.subject, cfg.ns[cat]))
    g.add((class_uri, DC.source, Literal(source_tag)))

    # simpleContent → enumeration or datatype alias
    simple_content = ct_element.find(f"{XSD_PRE}simpleContent")
    if simple_content is not None:
        restriction = simple_content.find(f"{XSD_PRE}restriction")
        extension   = simple_content.find(f"{XSD_PRE}extension")
        base_elem   = restriction if restriction is not None else extension
        if base_elem is not None:
            base_local = _local(base_elem.get("base", ""))
            enums = [
                e.get("value")
                for e in base_elem.findall(f"{XSD_PRE}enumeration")
                if e.get("value")
            ]
            if enums:
                g.add((class_uri, OWL.oneOf, _build_enum_list(g, class_uri, enums, cfg)))
                g.add((class_uri, RDFS.comment,
                       Literal(f"Enumeration. Allowed values: {', '.join(enums)}")))
            if base_local in XSD_TYPE_MAP:
                g.add((class_uri, SKOS.notation,
                       Literal(f"xsd:{base_local}", datatype=XSD.string)))
        return

    # sequence / choice / all children → properties
    for seq_elem in ct_element.iter(f"{XSD_PRE}element"):
        elem_name  = seq_elem.get("name", "")
        elem_type  = seq_elem.get("type", "")
        min_occurs = seq_elem.get("minOccurs", "1")
        max_occurs = seq_elem.get("maxOccurs", "1")
        ref        = seq_elem.get("ref", "")

        prop_name = elem_name or _local(ref)
        if not prop_name:
            continue

        prop_uri    = cfg.prop_uri(type_name, prop_name)
        shared_property = cfg.is_shared_property(prop_name)
        range_local = _local(elem_type) if elem_type else _extract_inline_simple_base(seq_elem)

        # Strict mode avoids asserting property semantics with no type evidence.
        if strict_semantics and not range_local and seq_elem.find(f"{XSD_PRE}complexType") is None:
            continue

        # Enhanced property classification with OWL2 characteristics
        #  1. Direct XSD primitive (e.g. xs:string, xs:dateTime)
        #  2. simpleContent/simpleType wrapper resolving to an XSD primitive
        #  3. Reference to another complexType  →  ObjectProperty
        if range_local in XSD_TYPE_MAP:
            if prop_kinds.get(prop_uri) not in (None, "datatype"):
                continue
            prop_kinds[prop_uri] = "datatype"
            # Tier 1: raw primitive
            g.add((prop_uri, RDF.type,   OWL.DatatypeProperty))
            g.add((prop_uri, RDFS.range, XSD_TYPE_MAP[range_local]))
            
            # Add functional property characteristic for single-valued primitives
            if max_occurs == "1":
                g.add((prop_uri, RDF.type, OWL.FunctionalProperty))
                
        elif range_local in simple_types:
            if prop_kinds.get(prop_uri) not in (None, "datatype"):
                continue
            prop_kinds[prop_uri] = "datatype"
            # Tier 2: wrapper type that resolves to a primitive
            g.add((prop_uri, RDF.type,   OWL.DatatypeProperty))
            g.add((prop_uri, RDFS.range, simple_types[range_local]))
            
            # Add functional property characteristic for single-valued types
            if max_occurs == "1":
                g.add((prop_uri, RDF.type, OWL.FunctionalProperty))
                
        else:
            if prop_kinds.get(prop_uri) not in (None, "object"):
                continue
            prop_kinds[prop_uri] = "object"
            # Tier 3: reference to a real class
            g.add((prop_uri, RDF.type, OWL.ObjectProperty))
            if range_local:
                range_class_uri = _ensure_class_stub(g, cfg, range_local, source_tag)
                g.add((prop_uri, RDFS.range, range_class_uri))
                
                # Add functional property characteristic for single-valued objects
                if max_occurs == "1":
                    g.add((prop_uri, RDF.type, OWL.FunctionalProperty))
                
                # Generate inverse property for bidirectional relationships
                if not shared_property:
                    inverse_prop_name = f"inverse{_safe_uri_name(prop_name)}"
                    inverse_prop_uri = cfg.prop_uri(_local(range_local), inverse_prop_name)
                    g.add((inverse_prop_uri, RDF.type, OWL.ObjectProperty))
                    g.add((inverse_prop_uri, RDFS.label, Literal(f"inverse of {prop_name}")))
                    g.add((inverse_prop_uri, RDFS.comment, Literal(
                        f"Auto-generated inverse property for '{prop_name}' from {type_name}."
                    )))
                    g.add((inverse_prop_uri, DC.source, Literal(source_tag)))
                    g.add((inverse_prop_uri, RDFS.domain, range_class_uri))
                    g.add((inverse_prop_uri, RDFS.range, class_uri))
                    g.add((prop_uri, OWL.inverseOf, inverse_prop_uri))
                    g.add((inverse_prop_uri, OWL.inverseOf, prop_uri))
            else:
                _ensure_owl_thing_metadata(g, source_tag)
                g.add((prop_uri, RDFS.range, OWL.Thing))

        g.add((prop_uri, RDFS.domain,  class_uri))
        g.add((prop_uri, RDFS.label,   Literal(prop_name)))

        prop_annotation = _extract_annotation(seq_elem)
        if prop_annotation:
            g.add((prop_uri, RDFS.comment,    Literal(prop_annotation)))
            g.add((prop_uri, SKOS.definition, Literal(prop_annotation)))
        else:
            g.add((prop_uri, RDFS.comment, Literal(
                f"Property '{prop_name}' of {type_name}. "
                f"minOccurs={min_occurs} maxOccurs={max_occurs}."
            )))
        
        g.add((prop_uri, DC.source, Literal(source_tag)))

        # Emitting OWL Definitions for cardinality semantics
        min_v = 0 if min_occurs == "unbounded" else int(min_occurs)
        max_v = None if max_occurs == "unbounded" else int(max_occurs)

        if min_v > 0 or max_v is not None:
            restriction = BNode()
            g.add((restriction, RDF.type, OWL.Restriction))
            g.add((restriction, OWL.onProperty, prop_uri))
            
            if min_v > 0:
                g.add((restriction, OWL.minCardinality, Literal(min_v, datatype=XSD.nonNegativeInteger)))
            if max_v is not None:
                g.add((restriction, OWL.maxCardinality, Literal(max_v, datatype=XSD.nonNegativeInteger)))
                
            g.add((class_uri, RDFS.subClassOf, restriction))

        # Emitting OSLC Property rules
        oslc_prop = BNode()
        g.add((class_uri, OSLC.property, oslc_prop))
        g.add((oslc_prop, RDF.type, OSLC.Property))
        g.add((oslc_prop, OSLC.propertyDefinition, prop_uri))
        g.add((oslc_prop, OSLC.name, Literal(prop_name)))
        g.add((oslc_prop, OSLC.occurs, _get_oslc_occurs(min_occurs, max_occurs)))

    # xs:attribute elements → properties
    for attr_elem in ct_element.iter(f"{XSD_PRE}attribute"):
        attr_name  = attr_elem.get("name", "")
        attr_type  = attr_elem.get("type", "")
        attr_use   = attr_elem.get("use", "optional")  # "required" or "optional" (default)
        ref        = attr_elem.get("ref", "")

        prop_name = attr_name or _local(ref)
        if not prop_name:
            continue

        prop_uri    = cfg.prop_uri(type_name, prop_name)
        shared_property = cfg.is_shared_property(prop_name)
        range_local = _local(attr_type) if attr_type else _extract_inline_simple_base(attr_elem)

        if strict_semantics and not range_local:
            continue

        # Map use attribute to minOccurs/maxOccurs cardinality
        # use="required" → minOccurs=1, maxOccurs=1
        # use="optional" or missing → minOccurs=0, maxOccurs=1
        min_occurs = "1" if attr_use == "required" else "0"
        max_occurs = "1"  # Attributes are always single-valued
        min_v = int(min_occurs)
        max_v = int(max_occurs)

        # Classify property type — three tiers (identical to element logic)
        #  1. Direct XSD primitive (e.g. xs:string, xs:dateTime)
        #  2. simpleContent/simpleType wrapper resolving to an XSD primitive
        #  3. Reference to another complexType  →  ObjectProperty
        if range_local in XSD_TYPE_MAP:
            if prop_kinds.get(prop_uri) not in (None, "datatype"):
                continue
            prop_kinds[prop_uri] = "datatype"
            # Tier 1: raw primitive
            g.add((prop_uri, RDF.type,   OWL.DatatypeProperty))
            g.add((prop_uri, RDFS.range, XSD_TYPE_MAP[range_local]))
        elif range_local in simple_types:
            if prop_kinds.get(prop_uri) not in (None, "datatype"):
                continue
            prop_kinds[prop_uri] = "datatype"
            # Tier 2: wrapper type that resolves to a primitive
            g.add((prop_uri, RDF.type,   OWL.DatatypeProperty))
            g.add((prop_uri, RDFS.range, simple_types[range_local]))
        else:
            if prop_kinds.get(prop_uri) not in (None, "object"):
                continue
            prop_kinds[prop_uri] = "object"
            # Tier 3: reference to a real class
            g.add((prop_uri, RDF.type, OWL.ObjectProperty))
            if range_local:
                range_class_uri = _ensure_class_stub(g, cfg, range_local, source_tag)
                g.add((prop_uri, RDFS.range, range_class_uri))
            else:
                _ensure_owl_thing_metadata(g, source_tag)
                g.add((prop_uri, RDFS.range, OWL.Thing))

        g.add((prop_uri, RDFS.domain,  class_uri))
        g.add((prop_uri, RDFS.label,   Literal(prop_name)))

        attr_annotation = _extract_annotation(attr_elem)
        if attr_annotation:
            g.add((prop_uri, RDFS.comment,    Literal(attr_annotation)))
            g.add((prop_uri, SKOS.definition, Literal(attr_annotation)))
        else:
            g.add((prop_uri, RDFS.comment, Literal(
                f"Attribute '{prop_name}' of {type_name}. use={attr_use}."
            )))
        
        g.add((prop_uri, DC.source, Literal(source_tag)))

        # Emitting OWL Definitions for cardinality semantics
        if min_v > 0 or max_v is not None:
            restriction = BNode()
            g.add((restriction, RDF.type, OWL.Restriction))
            g.add((restriction, OWL.onProperty, prop_uri))
            
            if min_v > 0:
                g.add((restriction, OWL.minCardinality, Literal(min_v, datatype=XSD.nonNegativeInteger)))
            if max_v is not None:
                g.add((restriction, OWL.maxCardinality, Literal(max_v, datatype=XSD.nonNegativeInteger)))
                
            g.add((class_uri, RDFS.subClassOf, restriction))

        # Emitting OSLC Property rules
        oslc_prop = BNode()
        g.add((class_uri, OSLC.property, oslc_prop))
        g.add((oslc_prop, RDF.type, OSLC.Property))
        g.add((oslc_prop, OSLC.propertyDefinition, prop_uri))
        g.add((oslc_prop, OSLC.name, Literal(prop_name)))
        g.add((oslc_prop, OSLC.occurs, _get_oslc_occurs(min_occurs, str(max_occurs))))


def _build_enum_list(g: Graph, class_uri: URIRef,
                     values: list, cfg: OntologyConfig) -> BNode:
    """Build an rdf:List of owl:NamedIndividual enumeration values."""
    local_name = str(class_uri).split("#")[-1].split("/")[-1]
    individuals = []
    for v in values:
        ind = cfg.ns[f"{local_name}_{_safe_uri_name(v)}"]
        g.add((ind, RDF.type,      OWL.NamedIndividual))
        g.add((ind, RDF.type,      class_uri))
        g.add((ind, RDFS.label,    Literal(v)))
        g.add((ind, SKOS.notation, Literal(v)))
        individuals.append(ind)

    if not individuals:
        return RDF.nil
    head = current = BNode()
    for i, ind in enumerate(individuals):
        g.add((current, RDF.first, ind))
        if i < len(individuals) - 1:
            nxt = BNode()
            g.add((current, RDF.rest, nxt))
            current = nxt
        else:
            g.add((current, RDF.rest, RDF.nil))
    return head


def process_xsd_file(g: Graph, xsd_path: Path,
                     seen_classes: set, cfg: OntologyConfig,
                     simple_types: dict, prop_kinds: dict,
                     strict_semantics: bool = True) -> None:
    """Parse one XSD file and add its complexTypes / top-level elements to the graph."""
    try:
        root = ET.parse(xsd_path).getroot()
    except ET.ParseError as e:
        logger.warning("parse error in %s: %s", xsd_path.name, e)
        return

    file_stem   = xsd_path.stem.split(" ")[0]  # strip timestamp suffix
    source_tag  = f"{cfg.source_standard or cfg.prefix} / {file_stem}"

    for ct in root.findall(f"{XSD_PRE}complexType"):
        parse_complex_type(
            g,
            ct,
            file_stem,
            seen_classes,
            cfg,
            simple_types,
            prop_kinds,
            strict_semantics=strict_semantics,
        )

    for el in root.findall(f"{XSD_PRE}element"):
        el_name = el.get("name", "")
        el_type = el.get("type", "")
        el_type_local = _local(el_type) if el_type else _extract_inline_simple_base(el)

        if not el_name:
            continue
        if strict_semantics and not el_type_local:
            continue
        inst_uri = cfg.class_uri(el_name)
        if inst_uri in seen_classes:
            continue
        seen_classes.add(inst_uri)
        cat = cfg.category_for(el_name)
        g.add((inst_uri, RDF.type,         OWL.Class))
        if el_type_local in XSD_TYPE_MAP:
            g.add((inst_uri, SKOS.notation, Literal(f"xsd:{el_type_local}", datatype=XSD.string)))
        elif el_type_local in simple_types:
            g.add((inst_uri, SKOS.notation, Literal(str(simple_types[el_type_local]))))
        elif el_type_local:
            g.add((inst_uri, RDFS.subClassOf, cfg.class_uri(el_type_local)))
        g.add((inst_uri, RDFS.label,       Literal(el_name)))

        elem_annotation = _extract_annotation(el)
        if elem_annotation:
            g.add((inst_uri, RDFS.comment,    Literal(elem_annotation)))
            g.add((inst_uri, SKOS.definition, Literal(elem_annotation)))
        else:
            g.add((inst_uri, RDFS.comment,     Literal(
                f"Top-level element '{el_name}' (type: {el_type_local}). Source: {file_stem}"
            )))

        if cfg.categories:
            g.add((inst_uri, DCTERMS.subject, cfg.ns[cat]))
        g.add((inst_uri, DC.source, Literal(source_tag)))

    logger.info("XSD processed: %s", file_stem)


def _add_xsd_provenance(
    g: Graph,
    ontology_uri: URIRef,
    cfg: OntologyConfig,
    xsd_paths: list[Path],
) -> None:
    """Attach schema-file provenance so ontology assertions are auditable."""
    for schema_file in sorted(xsd_paths):
        src_local = _safe_uri_name(f"source_{schema_file.stem}_{schema_file.suffix[1:]}")
        src_uri = cfg.ns[src_local]
        g.add((src_uri, RDF.type, PROV.Entity))
        g.add((src_uri, RDFS.label, Literal(schema_file.name)))
        g.add((src_uri, DCTERMS.format, Literal("application/xml")))
        g.add((ontology_uri, PROV.wasDerivedFrom, src_uri))
        g.add((ontology_uri, cfg.ns.hasSchemaFile, Literal(str(schema_file))))
        try:
            g.add((src_uri, DCTERMS.source, URIRef(schema_file.resolve().as_uri())))
        except Exception:
            g.add((src_uri, DCTERMS.source, Literal(str(schema_file))))


def find_xsd_file(schema_dir: Path, base_name: str,
                  timestamp_preference: list) -> "Path | None":
    """Find the preferred timestamped version of a schema file, falling back to any match."""
    for ts in timestamp_preference:
        candidates = list(schema_dir.glob(f"{base_name} ({ts}*).xsd"))
        if candidates:
            return candidates[0]
    candidates = sorted(schema_dir.glob(f"{base_name}*.xsd"))
    return candidates[-1] if candidates else None


def build_bridge_pairs(g: Graph, cfg: OntologyConfig) -> None:
    """
    Create cross-standard bridge classes and mapsTo properties from cfg.bridge_pairs.
    Each entry: (source_type_name, bridge_concept_name, comment)
    """
    if not cfg.bridge_pairs:
        return
    fallback_cat = list(cfg.categories.keys())[-1] if cfg.categories else None
    for src_type, bridge_name, comment in cfg.bridge_pairs:
        src_uri    = cfg.class_uri(src_type)
        bridge_uri = cfg.ns[f"bridge_{_safe_uri_name(bridge_name)}"]

        # Declare the domain class as an owl:Class stub when the XSD parse pass
        # has not already done so. bridge_pairs use source classes (e.g.
        # BatchProductionRecordType) as rdfs:domain, so they MUST be declared.
        if (src_uri, RDF.type, OWL.Class) not in g:
            g.add((src_uri, RDF.type,    OWL.Class))
            g.add((src_uri, RDFS.label,  Literal(src_type)))
            g.add((src_uri, RDFS.comment, Literal(
                f"Class from the source schema; domain of mapsTo_{_safe_uri_name(bridge_name)}."
            )))
            if fallback_cat:
                g.add((src_uri, DCTERMS.subject, cfg.ns[fallback_cat]))

        g.add((bridge_uri, RDF.type,      OWL.Class))
        g.add((bridge_uri, RDFS.label,    Literal(bridge_name.replace("_", " "))))
        g.add((bridge_uri, RDFS.comment,  Literal(comment)))
        if fallback_cat:
            g.add((bridge_uri, DCTERMS.subject, cfg.ns[fallback_cat]))

        prop_uri = cfg.ns[f"mapsTo_{_safe_uri_name(bridge_name)}"]
        g.add((prop_uri, RDF.type,      OWL.ObjectProperty))
        g.add((prop_uri, RDFS.domain,   src_uri))
        g.add((prop_uri, RDFS.range,    bridge_uri))
        g.add((prop_uri, RDFS.label,    Literal(f"mapsTo {bridge_name}")))
        g.add((prop_uri, RDFS.comment,  Literal(comment)))


# ── Main entry point ──────────────────────────────────────────────────────────

def convert_xsd_to_owl(cfg: OntologyConfig) -> Path:
    """
    Convert XSD files described by cfg into an OWL2/Turtle file.
    Works for any standard — pass the appropriate OntologyConfig.
    """
    schema_path = Path(cfg.schema_dir)
    output_path = (
        Path(cfg.output_ttl) if cfg.output_ttl
        else Path(__file__).resolve().parent.parent / "ontologies" / "generated" / "B2MML_TechTransfer.ttl"
    )

    print(f"\n{'='*60}")
    print(f"  XSD -> OWL2/Turtle Converter")
    print(f"  Standard   : {cfg.source_standard or cfg.title}")
    print(f"  Schema dir : {schema_path}")
    print(f"  Output     : {output_path}")
    print(f"{'='*60}\n")

    g = Graph()
    g.bind("",        cfg.ns)
    g.bind(cfg.prefix, cfg.ns)
    g.bind("owl",     OWL)
    g.bind("rdf",     RDF)
    g.bind("rdfs",    RDFS)
    g.bind("xsd",     XSD)
    g.bind("skos",    SKOS)
    g.bind("dc",      DC)
    g.bind("dcterms", DCTERMS)
    g.bind("sh",      SH)
    g.bind("oslc",    OSLC)
    g.bind("prov",    PROV)

    build_ontology_header(g, cfg)
    build_skos_categories(g, cfg)

    seen_classes: set = set()
    prop_kinds:   dict = {}
    missing:      list = []

    # If target_files is empty, auto-discover all XSD files in schema_dir
    targets = cfg.target_files or [
        p.stem.split(" ")[0]
        for p in sorted(schema_path.glob("*.xsd"))
    ]

    # Resolve target names to actual file paths
    xsd_paths = []
    for base_name in targets:
        xf = find_xsd_file(schema_path, base_name, cfg.timestamp_preference)
        if xf is None:
            logger.warning("Missing XSD target: %s", base_name)
            missing.append(base_name)
        else:
            xsd_paths.append(xf)

    # ── Pass 1: collect ALL simpleType/simpleContent wrappers across the entire
    # schema directory (not just the target files).  Many standards keep shared
    # primitive-wrapper types in a Common/CommonComponents file that is not
    # itself a conversion target but whose type definitions ARE needed for
    # correct DatatypeProperty vs ObjectProperty classification.
    all_schema_xsd = sorted(schema_path.glob("*.xsd"))
    strict_semantics = os.getenv("XSD_STRICT_SEMANTICS", "true").strip().lower() in {
        "1", "true", "yes", "on"
    }
    logger.info("Pass 1: scanning %d schema XSD files for simple-type wrappers...", len(all_schema_xsd))
    simple_types = _collect_simple_types(all_schema_xsd)
    logger.info("Found %d wrapper types resolving to XSD primitives", len(simple_types))

    ontology_uri = URIRef(cfg.base_uri)
    _add_xsd_provenance(g, ontology_uri, cfg, all_schema_xsd)

    # ── Pass 2: build the ontology graph ──────────────────────────────────────
    for xf in xsd_paths:
        process_xsd_file(
            g,
            xf,
            seen_classes,
            cfg,
            simple_types,
            prop_kinds,
            strict_semantics=strict_semantics,
        )

    build_bridge_pairs(g, cfg)

    # Derive OWL (RDF/XML) path from TTL path if not explicitly configured
    owl_path = (
        Path(cfg.output_owl) if cfg.output_owl
        else output_path.with_suffix(".owl")
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    g.serialize(destination=str(output_path), format="turtle")
    g.serialize(destination=str(owl_path), format="xml")

    triple_count = len(g)
    class_count  = sum(1 for _ in g.triples((None, RDF.type, OWL.Class)))
    dt_count     = sum(1 for _ in g.triples((None, RDF.type, OWL.DatatypeProperty)))
    op_count     = sum(1 for _ in g.triples((None, RDF.type, OWL.ObjectProperty)))
    prop_count   = dt_count + op_count

    logger.info("%s", '=' * 60)
    logger.info("Done. Triples: %s", f"{triple_count:,}")
    logger.info("Classes: %d", class_count)
    logger.info("Properties: %d", prop_count)
    logger.info("  DatatypeProperty: %d", dt_count)
    logger.info("  ObjectProperty: %d", op_count)
    if missing:
        logger.warning("Missing schema targets: %s", ', '.join(missing))
    logger.info("Output TTL: %s", output_path)
    logger.info("Output OWL: %s", owl_path)
    logger.info("%s", '=' * 60)
    return output_path


# Backwards-compat alias: old callers that used convert_b2mml_to_ttl(dir, ttl) still work
def convert_b2mml_to_ttl(schema_dir: str, output_ttl: str) -> Path:
    return convert_xsd_to_owl(b2mml_config(schema_dir=schema_dir, output_ttl=output_ttl))


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--config":
        cfg = OntologyConfig.from_json(sys.argv[2])
    elif len(sys.argv) == 2 and sys.argv[1] == "--env":
        cfg = OntologyConfig.from_env()
    elif len(sys.argv) >= 2 and sys.argv[1] == "--plmxml":
        # Usage: python parser_xsd.py --plmxml <schema_dir> [output.ttl]
        from pathlib import Path
        def plmxml_config(schema_dir: str = "", output_ttl: str = "") -> OntologyConfig:
            return OntologyConfig(
                base_uri         = "http://siemens.com/plmxml#",
                prefix           = "plmxml",
                title            = "Siemens PLMXML Ontology",
                description      = "Ontology generated from Siemens PLMXML XSD schemas.",
                creator          = "IAE — Industrial Autonomy and Engineering",
                source_ns        = "http://www.siemens.com/plmxml",
                source_standard  = "Siemens PLMXML 7.0.3",
                version_info     = "PLMXML-7.0.3",
                subject_keywords = "PLMXML, Siemens, PLM, BOM, EBOM, MBOM, BOP, Manufacturing",
                categories       = {
                    "PLMXML": ("PLMXML Root", "Root category for Siemens PLMXML ontology"),
                    "Product": ("Product", "Product and part definitions"),
                    "Assembly": ("Assembly", "Assembly and BOM structures"),
                    "Process": ("Process", "Manufacturing and process planning"),
                    "Resource": ("Resource", "Resources and assets"),
                    "Common": ("Common Types", "Shared/common types"),
                },
                category_map     = {
                    "Product": "Product",
                    "Part": "Product",
                    "Assembly": "Assembly",
                    "BOM": "Assembly",
                    "Process": "Process",
                    "Resource": "Resource",
                },
                category_hierarchy = ["Product", "Assembly", "Process", "Resource"],
                bridge_pairs     = [],
                target_files     = [],  # Auto-discover all XSDs
                schema_dir       = schema_dir or os.getenv("ONTO_SCHEMA_DIR", ""),
                output_ttl       = output_ttl or os.getenv("ONTO_OUTPUT_TTL") or (
                    str(Path(__file__).resolve().parent.parent / "ontologies" / "generated" / "PLMXML_Ontology.ttl")
                ),
                output_owl       = os.getenv("ONTO_OUTPUT_OWL") or (
                    str(Path(__file__).resolve().parent.parent / "ontologies" / "generated" / "PLMXML_Ontology.owl")
                ),
            )

        schema_dir = sys.argv[2] if len(sys.argv) > 2 else ""
        output_ttl = sys.argv[3] if len(sys.argv) > 3 else ""
        cfg = plmxml_config(schema_dir=schema_dir, output_ttl=output_ttl)
    else:
        cfg = b2mml_config(
            schema_dir = sys.argv[1] if len(sys.argv) > 1 else "",
            output_ttl = sys.argv[2] if len(sys.argv) > 2 else "",
        )
    convert_xsd_to_owl(cfg)
