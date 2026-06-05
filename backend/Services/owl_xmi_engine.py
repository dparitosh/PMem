"""
XMI → OWL2/Turtle Converter Engine
=====================================
Converts XMI files (ISO 10303 SMRL specification) into OWL2 ontology
in Turtle format, integrating with the main semantic processing pipeline.

Supports:
  • UML/SysML models from XMI files
  • System engineering models (MBSE)
  • Requirements engineering models
  • Component architecture models

Usage:
    from engines.parser_xmi import convert_xmi_to_ttl
    
    convert_xmi_to_ttl(
        xmi_path="model.xmi",
        output_path="ontology.ttl",
        base_uri="http://example.org/model#"
    )
"""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any
from rdflib import Graph, URIRef, Literal, RDF, RDFS, OWL, Namespace, BNode
from rdflib.namespace import DCTERMS, XSD, SKOS, DC
from dotenv import load_dotenv
from loguru import logger

# Use local XMI parser from backend Services
try:
    from .xmi_parser import XMIParser
except ImportError:
    from xmi_parser import XMIParser  # type: ignore

load_dotenv()

# Default namespaces for XMI models
_DEFAULT_XMI_NAMESPACES = {
    "xmi": Namespace("http://www.omg.org/XMI/"),
    "uml": Namespace("http://www.omg.org/spec/UML/20161101/"),
    "sysml": Namespace("http://www.omg.org/spec/SysML/20161101/SysML/"),
    "req": Namespace("http://www.omg.org/spec/ReqIF/20110401/reqif.xsd/"),
    "mbse": Namespace("http://standards.iso.org/iso/15926/ontology/mbse/"),
}

_TYPE_CLASS_HINTS = ["class", "block", "interface", "component", "system", "subsystem", "requirement", "usecase", "stakeholderneed", "actor", "activity", "signal", "valuetype", "constraintblock", "enumeration", "datatype", "interaction"]
_TYPE_PART_HINTS = ["part", "instance", "instancespecification", "object", "flowport", "itemflow"]
_TYPE_PACKAGE_HINTS = ["package", "model"]
_TYPE_ENUM_HINTS = ["enumeration", "enum"]
_TYPE_ATTRIBUTE_HINTS = ["attribute", "property", "slot"]
_TYPE_ASSOC_HINTS = ["association"]

_REL_GENERALIZATION_HINTS = ["generalization", "subclass", "extends", "inherit"]
_REL_COMPOSITION_HINTS = ["composition", "composite", "contains", "partof", "has_component"]
_REL_AGGREGATION_HINTS = ["aggregation", "aggregate", "shared"]
_REL_ASSOCIATION_HINTS = ["association", "relates_to", "connects_to"]
_REL_DEPENDENCY_HINTS = ["dependency", "depends_on", "uses"]
_REL_ALLOCATION_HINTS = ["allocation", "allocates", "allocated_to"]
_REL_INTERFACE_HINTS = ["interface_realization", "realization", "connects_to", "interface"]
# SysML-specific stereotyped dependency relationships
_REL_SATISFY_HINTS = ["satisfy"]
_REL_VERIFY_HINTS = ["verify"]
_REL_TRACE_HINTS = ["trace", "tracedto"]
_REL_REFINE_HINTS = ["refine"]
_REL_DERIVE_HINTS = ["derive_reqt", "derivereqt"]
# MagicGrid process-framework layer codes present in SugarPlantMBSE.xmi diagrams
_MAGICGRID_LAYER_LABELS = {
    "B1": "Stakeholder Needs",
    "W1": "Stakeholder Needs",
    "B1-W1": "Stakeholder Needs",
    "B2": "Use Cases",
    "B3": "System Context",
    "B4": "Measurements of Effectiveness",
    "W2": "Functional Analysis",
    "W3": "Logical Subsystem Communication",
    "W4": "Measurements of Effectiveness",
    "S1": "System Requirements",
    "S2": "System Behavior",
    "S3": "System Structure",
    "S4": "System Parameters",
}
PROV = Namespace("http://www.w3.org/ns/prov#")

_PRIMITIVE_TYPE_HINTS = {
    "string", "boolean", "bool", "integer", "int", "float", "double", "real",
    "decimal", "number", "date", "datetime", "time",
}

def _declare_core_mbse_vocabulary(g: Graph, ont_ns: Namespace) -> None:
    """Declare the three-layer MBSE pattern: OWL core, SKOS vocabulary, XMI instance links."""
    scheme_uri = ont_ns.MBSEConceptScheme
    source_tag = "XMI MBSE core vocabulary"
    g.add((SKOS.Concept, RDF.type, OWL.Class))
    g.add((SKOS.Concept, RDFS.label, Literal("Concept")))
    g.add((SKOS.Concept, RDFS.comment, Literal("SKOS concept class used as the vocabulary layer in the generated three-layer semantic model.")))
    g.add((SKOS.Concept, DCTERMS.source, Literal(source_tag)))
    g.add((scheme_uri, RDF.type, SKOS.ConceptScheme))
    g.add((scheme_uri, RDFS.label, Literal("MBSE Concept Scheme")))
    g.add((scheme_uri, SKOS.prefLabel, Literal("MBSE Concept Scheme")))
    g.add((scheme_uri, SKOS.definition, Literal("Controlled vocabulary for SysML/UML concepts extracted from XMI models using a three-layer semantic pattern.")))
    g.add((scheme_uri, DCTERMS.source, Literal(source_tag)))

    class_comments = {
        "Component": "Core OWL class for physical or logical system components extracted from XMI.",
        "Interface": "Core OWL class for interaction points and exposed interfaces extracted from XMI.",
        "Requirement": "Core OWL class for engineering requirements extracted from XMI.",
        "StakeholderNeed": "Core OWL class for stakeholder needs and concerns captured in the model.",
        "Function": "Core OWL class for behaviors, activities, or logical functions extracted from XMI.",
        "UseCase": "Core OWL class for UML use cases representing actor-goal interactions.",
        "Stereotype": "Core OWL class for UML or SysML stereotypes extracted from XMI.",
        "AllocationSource": "Core OWL class for elements that allocate responsibilities or resources.",
        "AllocationTarget": "Core OWL class for elements receiving allocations.",
        # Extended SysML 1.6 vocabulary
        "Actor": "Core OWL class for external actors that interact with the system (from UML/SysML Use Case models).",
        "Activity": "Core OWL class for system behaviors or functions modeled as UML/SysML Activities.",
        "ConstraintBlock": "Core OWL class for SysML Constraint Blocks used in parametric models.",
        "ValueType": "Core OWL class for SysML Value Types, including units of measure and primitive data types.",
        "FlowPort": "Core OWL class for SysML Flow Ports representing directional item flows on blocks.",
        "ItemFlow": "Core OWL class for SysML Item Flows conveying items through connectors.",
        "Signal": "Core OWL class for UML Signals representing asynchronous communications.",
        "State": "Core OWL class for UML/SysML States in state machine or activity models.",
    }
    for cls_name in list(class_comments.keys()):
        cls_uri = ont_ns[cls_name]
        g.add((cls_uri, RDF.type, OWL.Class))
        g.add((cls_uri, RDFS.label, Literal(cls_name)))
        g.add((cls_uri, RDFS.comment, Literal(class_comments[cls_name])))
        g.add((cls_uri, DCTERMS.source, Literal(source_tag)))

    g.add((ont_ns.Block, RDF.type, OWL.Class))
    g.add((ont_ns.Block, RDFS.label, Literal("Block")))
    g.add((ont_ns.Block, RDFS.comment, Literal("Compatibility OWL class for SysML blocks, modeled as a specialization of Component.")))
    g.add((ont_ns.Block, RDFS.subClassOf, ont_ns.Component))
    g.add((ont_ns.Block, DCTERMS.source, Literal(source_tag)))

    # ConstraintBlock and Activity are subclasses of Component/Function respectively
    g.add((ont_ns.ConstraintBlock, RDFS.subClassOf, ont_ns.Component))
    g.add((ont_ns.Activity, RDFS.subClassOf, ont_ns.Function))
    g.add((ont_ns.FlowPort, RDFS.subClassOf, ont_ns.Interface))
    g.add((ont_ns.ItemFlow, RDFS.subClassOf, ont_ns.Interface))

    # MagicGrid process-framework concept scheme
    mg_scheme_uri = ont_ns.MagicGridProcessScheme
    g.add((mg_scheme_uri, RDF.type, SKOS.ConceptScheme))
    g.add((mg_scheme_uri, RDFS.label, Literal("MagicGrid Process Framework")))
    g.add((mg_scheme_uri, SKOS.prefLabel, Literal("MagicGrid Process Framework")))
    g.add((mg_scheme_uri, SKOS.definition, Literal(
        "Controlled vocabulary for the MagicGrid MBSE methodology layers: "
        "B (black-box/stakeholder), W (white-box/functional), S (system definition)."
    )))
    g.add((mg_scheme_uri, DCTERMS.source, Literal(source_tag)))
    mg_layer_defs = {
        "B_Layer": (
            "Black-Box / Stakeholder Layer",
            "The Black-Box / Stakeholder layer in the MagicGrid framework captures stakeholder needs,"
            " goals, and system-level use cases from an external viewpoint.",
        ),
        "W_Layer": (
            "White-Box / Functional Layer",
            "The White-Box / Functional layer in the MagicGrid framework describes internal system"
            " functions, behaviors, and the logical architecture that satisfies stakeholder needs.",
        ),
        "S_Layer": (
            "System Definition Layer",
            "The System Definition layer in the MagicGrid framework specifies the physical and logical"
            " system architecture, component structure, and interface definitions.",
        ),
    }
    for code, (label, definition) in mg_layer_defs.items():
        c_uri = ont_ns[code]
        g.add((c_uri, RDF.type, SKOS.Concept))
        g.add((c_uri, RDFS.label, Literal(label)))
        g.add((c_uri, SKOS.prefLabel, Literal(label)))
        g.add((c_uri, SKOS.definition, Literal(definition)))
        g.add((c_uri, SKOS.inScheme, mg_scheme_uri))
        g.add((mg_scheme_uri, SKOS.hasTopConcept, c_uri))
        g.add((c_uri, DCTERMS.source, Literal(source_tag)))

    mbse_concept_specs = [
        ("ComponentConcept",      "Component",        "Vocabulary concept for physical or logical system components that make up the system architecture."),
        ("InterfaceConcept",      "Interface",        "Vocabulary concept for interaction points and exposed contracts between system elements."),
        ("RequirementConcept",    "Requirement",      "Vocabulary concept for engineering requirements capturing stakeholder and system-level constraints."),
        ("StakeholderNeedConcept","Stakeholder Need", "Vocabulary concept for stakeholder needs and concerns captured prior to formal requirement derivation."),
        ("FunctionConcept",       "Function",         "Vocabulary concept for behaviors, activities, or logical functions the system must perform."),
        ("UseCaseConcept",        "Use Case",         "Vocabulary concept for UML use cases representing actor-goal interactions with the system."),
        ("StereotypeConcept",     "Stereotype",       "Vocabulary concept for UML or SysML stereotypes applied as model extensions."),
        ("ActorConcept",          "Actor",            "Vocabulary concept for external actors that interact with the system in use case models."),
        ("ActivityConcept",       "Activity",         "Vocabulary concept for system behaviors or functions modeled as UML/SysML Activities."),
        ("ConstraintBlockConcept","Constraint Block", "Vocabulary concept for SysML Constraint Blocks used in parametric and mathematical models."),
        ("ValueTypeConcept",      "Value Type",       "Vocabulary concept for SysML Value Types including units of measure and primitive data types."),
        ("FlowPortConcept",       "Flow Port",        "Vocabulary concept for SysML Flow Ports representing directional item flows on blocks."),
        ("ItemFlowConcept",       "Item Flow",        "Vocabulary concept for SysML Item Flows conveying items through connectors between ports."),
        ("SignalConcept",         "Signal",           "Vocabulary concept for UML Signals representing asynchronous communication events."),
        ("StateConcept",          "State",            "Vocabulary concept for UML/SysML States in state machine or activity models."),
    ]
    for concept_name, label, definition in mbse_concept_specs:
        concept_uri = ont_ns[concept_name]
        g.add((concept_uri, RDF.type, SKOS.Concept))
        g.add((concept_uri, RDFS.label, Literal(label)))
        g.add((concept_uri, SKOS.prefLabel, Literal(label)))
        g.add((concept_uri, SKOS.definition, Literal(definition)))
        g.add((concept_uri, SKOS.inScheme, scheme_uri))
        g.add((scheme_uri, SKOS.hasTopConcept, concept_uri))
        g.add((concept_uri, SKOS.topConceptOf, scheme_uri))
        g.add((concept_uri, DCTERMS.source, Literal(source_tag)))

    property_specs = {
        "hasPart": ("has part", ont_ns.Component, ont_ns.Component, "Composition relation between component-level elements."),
        "dependsOn": ("depends on", ont_ns.Component, ont_ns.Component, "Dependency relation between component-level or function-level elements."),
        "allocatedTo": ("allocated to", ont_ns.AllocationSource, ont_ns.AllocationTarget, "Allocation relation between source and target engineering elements."),
        "hasInterface": ("has interface", ont_ns.Component, ont_ns.Interface, "Interface realization or exposure relation from a component to an interface."),
        "hasStereotype": ("has stereotype", OWL.Thing, ont_ns.Stereotype, "Applied stereotype relation from an XMI element to a stereotype class."),
        "hasRequirement": ("has requirement", ont_ns.Component, ont_ns.Requirement, "Traceability relation from an element to a requirement."),
        "hasVocabularyTerm": ("has vocabulary term", OWL.Thing, SKOS.Concept, "Links an OWL resource to its SKOS vocabulary concept."),
        "classifiedAs": ("classified as", OWL.Thing, SKOS.Concept, "Links an XMI instance to a SKOS vocabulary concept in the semantic layer."),
        # SysML-specific traceability properties
        "satisfies": ("satisfies", ont_ns.Component, ont_ns.Requirement, "SysML Satisfy: an element satisfies a requirement."),
        "verifies": ("verifies", ont_ns.Component, ont_ns.Requirement, "SysML Verify: a test case or verification element verifies a requirement."),
        "traces": ("traces", OWL.Thing, OWL.Thing, "SysML Trace: a weak refinement tracing between model elements."),
        "refines": ("refines", OWL.Thing, OWL.Thing, "SysML Refine: an element refines or elaborates another element."),
        "derivesFrom": ("derives from", ont_ns.Requirement, ont_ns.Requirement, "SysML DeriveReqt: a derived requirement derived from a source requirement."),
        "hasFlowPort": ("has flow port", ont_ns.Component, ont_ns.FlowPort, "Structural link from a block to one of its flow ports."),
        "carriesItemFlow": ("carries item flow", ont_ns.Interface, ont_ns.ItemFlow, "Link from a connector or interface to the item flow it carries."),
        # Inverse properties
        "isPartOf": ("is part of", ont_ns.Component, ont_ns.Component, "Inverse of hasPart: a component is a structural part of a larger component."),
        "isRequirementOf": ("is requirement of", ont_ns.Requirement, ont_ns.Component, "Inverse of hasRequirement."),
        "allocatedFrom": ("allocated from", ont_ns.AllocationTarget, ont_ns.AllocationSource, "Inverse of allocatedTo."),
    }

    core_flag_uri = ont_ns.isCoreVocabularyDefinition
    g.add((core_flag_uri, RDF.type, OWL.DatatypeProperty))
    g.add((core_flag_uri, RDFS.label, Literal("is core vocabulary definition")))
    g.add((core_flag_uri, RDFS.comment, Literal("True when a property is predeclared as part of the mapper core vocabulary, not inferred from a specific model edge.")))
    g.add((core_flag_uri, RDFS.domain, OWL.Thing))
    g.add((core_flag_uri, RDFS.range, XSD.boolean))
    g.add((core_flag_uri, DCTERMS.source, Literal(source_tag)))

    for prop_name, (prop_label, domain_uri, range_uri, prop_comment) in property_specs.items():
        prop_uri = ont_ns[prop_name]
        g.add((prop_uri, RDF.type, OWL.ObjectProperty))
        g.add((prop_uri, RDFS.label, Literal(prop_label)))
        g.add((prop_uri, RDFS.comment, Literal(prop_comment)))
        g.add((prop_uri, RDFS.domain, domain_uri))
        g.add((prop_uri, RDFS.range, range_uri))
        g.add((prop_uri, DCTERMS.source, Literal(source_tag)))
        g.add((prop_uri, core_flag_uri, Literal(True, datatype=XSD.boolean)))

    # Declare formal inverse pairs
    _inverse_pairs = [
        (ont_ns.hasPart, ont_ns.isPartOf),
        (ont_ns.hasRequirement, ont_ns.isRequirementOf),
        (ont_ns.allocatedTo, ont_ns.allocatedFrom),
    ]
    for fwd, inv in _inverse_pairs:
        g.add((fwd, OWL.inverseOf, inv))
        g.add((inv, OWL.inverseOf, fwd))

    # hasPart is transitive (structural decomposition hierarchy)
    g.add((ont_ns.hasPart, RDF.type, OWL.TransitiveProperty))
    # satisfies implies a traceability chain: use owl:ObjectProperty annotation only
    # (not declared transitive to avoid unintended closure over mixed types)

def convert_xmi_to_ttl(
    xmi_path: str,
    output_path: str,
    base_uri: str = "",
    title: str = "",
    comment: str = "",
    version_info: str = "1.0.0",
    extra_namespaces: Optional[Dict[str, Namespace]] = None,
    strict_semantics: Optional[bool] = None,
) -> bool:
    """
    Convert an XMI file to OWL2/Turtle ontology.
    
    Args:
        xmi_path: Path to the XMI file
        output_path: Path for the output TTL file
        base_uri: Base URI for the ontology (must end with # or /)
        title: Title for the ontology
        comment: Description/comment for the ontology
        version_info: Version information
        extra_namespaces: Additional namespaces to include
        strict_semantics: If True, avoid inferring class semantics when evidence is missing
        
    Returns:
        True if successful, False otherwise
    """
    try:
        logger.info(f"Converting XMI file: {xmi_path}")
        
        # Validate inputs
        xmi_file = Path(xmi_path)
        if not xmi_file.exists():
            raise FileNotFoundError(f"XMI file not found: {xmi_path}")
            
        if not base_uri:
            base_uri = os.getenv("IAE_BASE_URI", "http://example.org/xmi#")
        if not base_uri.endswith(('#', '/')):
            base_uri += '#'
            
        if not title:
            title = f"XMI Model Ontology - {xmi_file.stem}"
        if not comment:
            comment = f"OWL2 ontology generated from XMI file: {xmi_file.name}"
        if strict_semantics is None:
            strict_semantics = os.getenv("XMI_STRICT_SEMANTICS", "true").strip().lower() in {
                "1", "true", "yes", "on"
            }
            
        # Initialize RDF graph
        g = Graph()
        
        # Set up namespaces
        namespaces = _DEFAULT_XMI_NAMESPACES.copy()
        if extra_namespaces:
            namespaces.update(extra_namespaces)
            
        # Main ontology namespace
        ONT = Namespace(base_uri)
        namespaces["ont"] = ONT
        
        # Bind namespaces to graph
        for prefix, namespace in namespaces.items():
            g.bind(prefix, namespace)
        g.bind("dcterms", DCTERMS)
        g.bind("prov", PROV)
        g.bind("skos", SKOS)

        _declare_core_mbse_vocabulary(g, ONT)
            
        # Create ontology header
        ontology_uri = URIRef(base_uri.rstrip('#/'))
        g.add((ontology_uri, RDF.type, OWL.Ontology))
        g.add((ontology_uri, RDFS.label, Literal(title)))
        g.add((ontology_uri, RDFS.comment, Literal(comment)))
        g.add((ontology_uri, OWL.versionInfo, Literal(version_info)))
        g.add((ontology_uri, DCTERMS.created, Literal(datetime.now(timezone.utc).isoformat(), datatype=XSD.dateTime)))
        g.add((ontology_uri, DCTERMS.creator, Literal("GitHub Copilot XMI MBSE Mapper")))

        scheme_uri = ONT[f"{_safe_uri_name(xmi_file.stem)}_ConceptScheme"]
        g.add((scheme_uri, RDF.type, SKOS.ConceptScheme))
        g.add((scheme_uri, RDFS.label, Literal(f"{xmi_file.stem} MBSE Vocabulary")))
        g.add((scheme_uri, SKOS.prefLabel, Literal(f"{xmi_file.stem} MBSE Vocabulary")))
        g.add((scheme_uri, SKOS.definition, Literal(f"Vocabulary and taxonomy extracted from XMI model {xmi_file.name}.")))
        g.add((scheme_uri, DCTERMS.source, Literal(f"XMI / {xmi_file.name}")))
        
        # Parse XMI file
        parser = XMIParser()
        xmi_data = parser.parse(xmi_file)
        _add_xmi_provenance(g, ontology_uri, ONT, xmi_file, xmi_data)
        
        logger.info(f"Parsed {len(xmi_data['nodes'])} nodes and {len(xmi_data['relationships'])} relationships")
        
        # Convert nodes to OWL classes and individuals
        source_tag = f"XMI / {xmi_file.name}"
        _convert_xmi_nodes(g, xmi_data['nodes'], ONT, source_tag, scheme_uri)
        
        # Convert relationships to OWL properties
        _convert_xmi_relationships(
            g,
            xmi_data['relationships'],
            ONT,
            strict_semantics=strict_semantics,
            source_tag=source_tag,
            scheme_uri=scheme_uri,
        )

        # ── SKOS: declare hasTopConcept for the file-specific ConceptScheme ──
        # The MBSE core concepts (ComponentConcept, etc.) are declared in
        # MBSEConceptScheme and used as skos:broader by all model node concepts.
        # Pull them into this scheme as well so the hierarchy is self-contained,
        # then declare only them (not the 800+ leaves) as hasTopConcept.
        scheme_members = set(g.subjects(SKOS.inScheme, scheme_uri))
        external_broaders: set = set()
        for member in scheme_members:
            for b in g.objects(member, SKOS.broader):
                if b not in scheme_members:
                    external_broaders.add(b)
        for top_concept in external_broaders:
            if (top_concept, SKOS.inScheme, scheme_uri) not in g:
                g.add((top_concept, SKOS.inScheme, scheme_uri))
            if (scheme_uri, SKOS.hasTopConcept, top_concept) not in g:
                g.add((scheme_uri, SKOS.hasTopConcept, top_concept))
                g.add((top_concept, SKOS.topConceptOf, scheme_uri))

        # Write to TTL file
        _apply_graph_quality_baseline(
            g,
            ont_ns=ONT,
            source_tag=source_tag,
            creator_text="GitHub Copilot XMI MBSE Mapper",
            version_text=version_info,
        )

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(g.serialize(format='turtle'))
            
        logger.info(f"Successfully converted XMI to TTL: {output_path}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to convert XMI to TTL: {e}")
        return False

def _convert_xmi_nodes(
    g: Graph,
    nodes: List[Dict[str, Any]],
    ont_ns: Namespace,
    source_tag: str,
    scheme_uri: URIRef,
) -> None:
    """Convert XMI nodes into OWL classes, individuals, and properties."""
    
    for node in nodes:
        props = node.get("properties", {})
        node_id = props.get("id", "")
        node_type = props.get("type", "")
        node_name = str(props.get("name") or "").strip()
        label = node.get("label", "Element")
        target_type = str(props.get("targetType") or props.get("attr_type") or "")
        stereotype_raw = str(props.get("stereotype") or props.get("appliedStereotype") or "")
        definition_text = _choose_definition_text(props, node_name, label)
        owner_id = str(props.get("ownerId") or "")
        
        if not node_id:
            continue
            
        # Create URI for the node
        safe_id = _safe_uri_name(node_id)
        node_uri = ont_ns[safe_id]
        
        semantic_kind = _node_semantic_kind(node_type, label, node_name, props)
        core_class_uri = _infer_core_semantic_class(ont_ns, node_type, label, node_name, props, semantic_kind)
        node_concept_uri = _ensure_vocab_concept(
            g,
            ont_ns,
            raw_id=node_id,
            display_label=node_name or _humanize_xmi_identifier(node_id, semantic_kind),
            source_tag=source_tag,
            scheme_uri=scheme_uri,
            broader_concept_uri=_core_concept_for_class(ont_ns, core_class_uri),
            definition_text=definition_text,
        )

        # SysML/UML element semantics
        if semantic_kind == "class":
            g.add((node_uri, RDF.type, OWL.Class))
            g.add((node_uri, RDFS.subClassOf, core_class_uri))
            g.add((node_uri, ont_ns.hasVocabularyTerm, node_concept_uri))
            if label:
                parent_class_uri = ont_ns[_safe_uri_name(label)]
                g.add((parent_class_uri, RDF.type, OWL.Class))
                g.add((parent_class_uri, RDFS.label, Literal(label)))
                g.add((parent_class_uri, RDFS.comment, Literal(f"MBSE parent classification for {label}.")))
                g.add((parent_class_uri, DCTERMS.source, Literal(source_tag)))
                g.add((node_uri, RDFS.subClassOf, parent_class_uri))
        elif semantic_kind == "package":
            # Package is modeled as a conceptual container class.
            g.add((node_uri, RDF.type, OWL.Class))
            g.add((node_uri, RDFS.subClassOf, core_class_uri))
            g.add((node_uri, ont_ns.hasVocabularyTerm, node_concept_uri))
        elif semantic_kind == "enumeration":
            g.add((node_uri, RDF.type, OWL.Class))
            g.add((node_uri, RDFS.subClassOf, core_class_uri))
            g.add((node_uri, ont_ns.hasVocabularyTerm, node_concept_uri))
            for literal_name in _extract_enumeration_literals(props):
                lit_uri = ont_ns[_safe_uri_name(f"{node_id}_{literal_name}")]
                g.add((lit_uri, RDF.type, OWL.NamedIndividual))
                g.add((lit_uri, RDF.type, node_uri))
                g.add((lit_uri, RDF.type, core_class_uri))
                g.add((lit_uri, ont_ns.classifiedAs, node_concept_uri))
                g.add((lit_uri, RDFS.label, Literal(literal_name)))
        elif semantic_kind == "datatype_property":
            g.add((node_uri, RDF.type, OWL.DatatypeProperty))
            g.add((node_uri, RDFS.domain, _owner_class_uri(g, ont_ns, owner_id, source_tag, scheme_uri)))
            g.add((node_uri, RDFS.range, _infer_xsd_datatype(target_type)))
        elif semantic_kind == "object_property":
            g.add((node_uri, RDF.type, OWL.ObjectProperty))
            g.add((node_uri, RDFS.domain, _owner_class_uri(g, ont_ns, owner_id, source_tag, scheme_uri)))
            if target_type:
                target_uri = _ensure_xmi_class(g, ont_ns, target_type, source_tag, scheme_uri)
                g.add((node_uri, RDFS.range, target_uri))
            else:
                _ensure_owl_thing_metadata_xmi(g, source_tag)
                g.add((node_uri, RDFS.range, OWL.Thing))
        elif semantic_kind == "stereotype":
            g.add((node_uri, RDF.type, OWL.Class))
            g.add((node_uri, RDFS.subClassOf, ont_ns.Stereotype))
            g.add((node_uri, ont_ns.hasVocabularyTerm, node_concept_uri))
        else:
            # Part/instance semantics default to NamedIndividual.
            g.add((node_uri, RDF.type, OWL.NamedIndividual))
            g.add((node_uri, RDF.type, core_class_uri))
            g.add((node_uri, ont_ns.classifiedAs, node_concept_uri))
            if label:
                class_uri = ont_ns[_safe_uri_name(label)]
                g.add((class_uri, RDF.type, OWL.Class))
                g.add((class_uri, RDFS.label, Literal(label)))
                g.add((class_uri, RDFS.comment, Literal(f"Fallback classifier class derived from XMI label '{label}'.")))
                g.add((class_uri, DCTERMS.source, Literal(source_tag)))
                g.add((node_uri, RDF.type, class_uri))
                g.add((node_uri, ont_ns.hasVocabularyTerm, _ensure_vocab_concept(
                    g,
                    ont_ns,
                    raw_id=label,
                    display_label=label,
                    source_tag=source_tag,
                    scheme_uri=scheme_uri,
                    broader_concept_uri=_core_concept_for_class(ont_ns, core_class_uri),
                    definition_text=f"Vocabulary concept derived from XMI classifier '{label}'.",
                )))
        
        # Add properties
        if node_name:
            g.add((node_uri, RDFS.label, Literal(node_name)))
        else:
            fallback_label = _humanize_xmi_identifier(node_id, semantic_kind)
            g.add((node_uri, RDFS.label, Literal(fallback_label)))
        g.add((node_uri, DCTERMS.source, Literal(source_tag)))
        if definition_text:
            g.add((node_uri, RDFS.comment, Literal(definition_text)))
            
        g.add((node_uri, ont_ns.hasXMIType, Literal(node_type)))
        g.add((node_uri, ont_ns.hasXMIID, Literal(node_id)))

        # Annotate with MagicGrid process-framework layer concept if the name or
        # label carries a recognised grid-cell code (e.g. "B2 Use Cases", "S1 System Requirements").
        _annotate_magicgrid_layer(g, node_uri, node_name or label, ont_ns, source_tag)
        
        # Add additional properties from XMI attributes
        for prop_name, prop_value in props.items():
            if prop_name not in ["id", "type", "name"] and prop_value:
                prop_uri = ont_ns[f"has{_safe_uri_name(prop_name)}"]
                g.add((prop_uri, RDF.type, OWL.DatatypeProperty))
                g.add((prop_uri, RDFS.label, Literal(_format_property_label(prop_name))))
                g.add((prop_uri, RDFS.comment, Literal(f"Generated XMI attribute property for {prop_name}.")))
                g.add((prop_uri, DCTERMS.source, Literal(source_tag)))
                g.add((prop_uri, RDFS.domain, OWL.Thing))
                g.add((prop_uri, RDFS.range, XSD.string))
                g.add((node_uri, prop_uri, Literal(str(prop_value))))

        if stereotype_raw:
            for st_name in [v.strip() for v in stereotype_raw.replace(";", ",").split(",") if v.strip()]:
                st_uri = ont_ns[_safe_uri_name(st_name)]
                g.add((st_uri, RDF.type, OWL.Class))
                g.add((st_uri, RDFS.subClassOf, ont_ns.Stereotype))
                g.add((st_uri, RDFS.label, Literal(st_name)))
                g.add((st_uri, DCTERMS.source, Literal(source_tag)))
                g.add((node_uri, ont_ns.hasStereotype, st_uri))
                g.add((st_uri, ont_ns.hasVocabularyTerm, _ensure_vocab_concept(
                    g,
                    ont_ns,
                    raw_id=st_name,
                    display_label=st_name,
                    source_tag=source_tag,
                    scheme_uri=scheme_uri,
                    broader_concept_uri=ont_ns.StereotypeConcept,
                    definition_text=f"Stereotype vocabulary concept '{st_name}' extracted from XMI.",
                )))

def _convert_xmi_relationships(
    g: Graph,
    relationships: List[Dict[str, Any]],
    ont_ns: Namespace,
    strict_semantics: bool = True,
    source_tag: str = "",
    scheme_uri: URIRef | None = None,
) -> None:
    """Convert XMI relationships to OWL object properties and subclass semantics."""
    
    for rel in relationships:
        rel_type = rel.get("type", "RELATES_TO")
        from_props = rel.get("from_props", {})
        to_props = rel.get("to_props", {})
        
        from_id = from_props.get("id")
        to_id = to_props.get("id")
        
        if not from_id or not to_id:
            continue
            
        # Create URIs
        from_uri = ont_ns[_safe_uri_name(from_id)]
        to_uri = ont_ns[_safe_uri_name(to_id)]

        if _matches_any(rel_type, _REL_GENERALIZATION_HINTS):
            if strict_semantics and not (_is_class_like(g, from_uri) and _is_class_like(g, to_uri)):
                generalization_prop = ont_ns["generalization"]
                g.add((generalization_prop, RDF.type, OWL.ObjectProperty))
                g.add((generalization_prop, RDFS.label, Literal("Generalization")))
                g.add((from_uri, generalization_prop, to_uri))
            else:
                g.add((from_uri, RDFS.subClassOf, to_uri))
                if _is_concept_like(g, from_uri) and _is_concept_like(g, to_uri):
                    g.add((from_uri, SKOS.broader, to_uri))
                    g.add((to_uri, SKOS.narrower, from_uri))
            continue
        
        rel_norm = _normalize_token(rel_type)
        if _matches_any(rel_type, _REL_COMPOSITION_HINTS):
            prop_uri = ont_ns.hasPart
        elif _matches_any(rel_type, _REL_SATISFY_HINTS):
            prop_uri = ont_ns.satisfies
        elif _matches_any(rel_type, _REL_VERIFY_HINTS):
            prop_uri = ont_ns.verifies
        elif _matches_any(rel_type, _REL_TRACE_HINTS):
            prop_uri = ont_ns.traces
        elif _matches_any(rel_type, _REL_REFINE_HINTS):
            prop_uri = ont_ns.refines
        elif _matches_any(rel_type, _REL_DERIVE_HINTS):
            prop_uri = ont_ns.derivesFrom
        elif _matches_any(rel_type, _REL_DEPENDENCY_HINTS):
            prop_uri = ont_ns.dependsOn
        elif _matches_any(rel_type, _REL_ALLOCATION_HINTS):
            prop_uri = ont_ns.allocatedTo
        elif _matches_any(rel_type, _REL_INTERFACE_HINTS):
            prop_uri = ont_ns.hasInterface
        elif "require" in rel_norm or "satisf" in rel_norm:
            prop_uri = ont_ns.hasRequirement
        elif _resource_has_semantic_type(g, to_uri, ont_ns.Interface):
            prop_uri = ont_ns.hasInterface
        elif _resource_has_semantic_type(g, to_uri, ont_ns.Requirement):
            prop_uri = ont_ns.hasRequirement
        else:
            prop_uri = ont_ns[_safe_uri_name(rel_type.lower())]

        g.add((prop_uri, RDF.type, OWL.ObjectProperty))
        
        # Add relationship
        g.add((from_uri, prop_uri, to_uri))
        
        # Add property metadata
        rel_label = _format_property_label(rel_type)
        g.add((prop_uri, RDFS.label, Literal(rel_label)))
        if source_tag:
            g.add((prop_uri, DCTERMS.source, Literal(source_tag)))

        if _matches_any(rel_type, _REL_COMPOSITION_HINTS):
            _add_all_values_from_restriction(g, from_uri, prop_uri, to_uri, strict_semantics=strict_semantics)
            # Existential restriction: a composite class has *some* part of the target type
            _add_some_values_from_restriction(g, from_uri, prop_uri, to_uri, strict_semantics=strict_semantics)

        if _matches_any(rel_type, _REL_ALLOCATION_HINTS):
            _apply_allocation_domain_constraints(g, ont_ns, prop_uri, from_uri, to_uri, strict_semantics=strict_semantics)
        else:
            _apply_inferred_domain_range(g, prop_uri, from_uri, to_uri, strict_semantics=strict_semantics)

        if _matches_any(rel_type, _REL_AGGREGATION_HINTS):
            g.add((prop_uri, RDFS.comment, Literal("Aggregation relation without ownership semantics")))

        if _matches_any(rel_type, _REL_DEPENDENCY_HINTS):
            g.add((prop_uri, RDFS.comment, Literal("Dependency relation with weak semantic coupling")))

        if _matches_any(rel_type, _REL_SATISFY_HINTS):
            g.add((prop_uri, RDFS.comment, Literal("SysML Satisfy: the source element fulfils the target requirement.")))
        if _matches_any(rel_type, _REL_VERIFY_HINTS):
            g.add((prop_uri, RDFS.comment, Literal("SysML Verify: the source test case or procedure verifies the target requirement.")))
        if _matches_any(rel_type, _REL_TRACE_HINTS):
            g.add((prop_uri, RDFS.comment, Literal("SysML Trace: weak traceability link between model artefacts.")))
        if _matches_any(rel_type, _REL_REFINE_HINTS):
            g.add((prop_uri, RDFS.comment, Literal("SysML Refine: the source element elaborates or refines the target.")))
        if _matches_any(rel_type, _REL_DERIVE_HINTS):
            g.add((prop_uri, RDFS.comment, Literal("SysML DeriveReqt: the source requirement is derived from the target requirement.")))

        if _is_concept_like(g, from_uri) and _is_concept_like(g, to_uri):
            if not _matches_any(rel_type, _REL_COMPOSITION_HINTS):
                g.add((from_uri, SKOS.related, to_uri))
                g.add((to_uri, SKOS.related, from_uri))
            if scheme_uri is not None:
                g.add((from_uri, SKOS.inScheme, scheme_uri))
                g.add((to_uri, SKOS.inScheme, scheme_uri))

def _annotate_magicgrid_layer(
    g: Graph,
    node_uri: URIRef,
    text: str,
    ont_ns: Namespace,
    source_tag: str,
) -> None:
    """Link a node to its MagicGrid process-framework concept when the element
    name/label starts with a recognised grid code (e.g. 'B2 Use Cases')."""
    import re
    if not text:
        return
    m = re.match(r"^([BWS][1-4](?:-[BWS][1-4])?)\b", text.strip(), re.IGNORECASE)
    if not m:
        return
    code = m.group(1).upper()
    long_label = _MAGICGRID_LAYER_LABELS.get(code)
    if not long_label:
        return
    concept_uri = ont_ns[f"MagicGrid_{_safe_uri_name(code)}"]
    if (concept_uri, RDF.type, SKOS.Concept) not in g:
        g.add((concept_uri, RDF.type, SKOS.Concept))
        g.add((concept_uri, RDFS.label, Literal(f"{code}: {long_label}")))
        g.add((concept_uri, SKOS.prefLabel, Literal(f"{code}: {long_label}")))
        g.add((concept_uri, SKOS.definition, Literal(
            f"MagicGrid MBSE process framework cell '{code}': {long_label}."
        )))
        g.add((concept_uri, SKOS.inScheme, ont_ns.MagicGridProcessScheme))
        g.add((concept_uri, DCTERMS.source, Literal(source_tag)))
        # Assign to the correct top-layer concept
        if code.startswith("B"):
            g.add((concept_uri, SKOS.broader, ont_ns.B_Layer))
        elif code.startswith("W"):
            g.add((concept_uri, SKOS.broader, ont_ns.W_Layer))
        elif code.startswith("S"):
            g.add((concept_uri, SKOS.broader, ont_ns.S_Layer))
    g.add((node_uri, ont_ns.hasMagicGridContext, concept_uri))
    # Declare the annotation property if not yet present
    prop_uri = ont_ns.hasMagicGridContext
    if (prop_uri, RDF.type, OWL.ObjectProperty) not in g:
        g.add((prop_uri, RDF.type, OWL.ObjectProperty))
        g.add((prop_uri, RDFS.label, Literal("has MagicGrid context")))
        g.add((prop_uri, RDFS.comment, Literal(
            "Links a model element to its MagicGrid MBSE process-framework layer concept."
        )))
        g.add((prop_uri, RDFS.domain, OWL.Thing))
        g.add((prop_uri, RDFS.range, SKOS.Concept))
        g.add((prop_uri, DCTERMS.source, Literal(source_tag)))


def _is_type_definition(xmi_type: str) -> bool:
    """Determine if XMI type represents a type definition (class) or instance."""
    type_indicators = [
        "Class", "Package", "Component", "Interface", 
        "Block", "Requirement", "System", "Subsystem"
    ]
    return any(indicator in xmi_type for indicator in type_indicators)

def _node_semantic_kind(xmi_type: str, label: str, name: str, props: Dict[str, Any]) -> str:
    """Map SysML/UML element type to an OWL semantic kind."""
    t_norm = _normalize_token(xmi_type)
    label_norm = _normalize_token(label)
    name_norm = _normalize_token(name)
    joined = f"{t_norm}{label_norm}{name_norm}"

    if "stereotype" in joined:
        return "stereotype"

    if _contains_any(t_norm, _TYPE_PACKAGE_HINTS):
        return "package"
    if _contains_any(t_norm, _TYPE_ENUM_HINTS):
        return "enumeration"
    if _contains_any(t_norm, _TYPE_ATTRIBUTE_HINTS):
        agg = _normalize_token(str(props.get("aggregation") or ""))
        target_type = _normalize_token(str(props.get("targetType") or props.get("attr_type") or ""))
        assoc = _normalize_token(str(props.get("association") or ""))
        if agg in {"composite", "shared"} or assoc or (target_type and target_type not in _PRIMITIVE_TYPE_HINTS):
            return "object_property"
        return "datatype_property"
    if _contains_any(t_norm, _TYPE_ASSOC_HINTS):
        return "object_property"
    # FlowPort / ItemFlow → NamedIndividual (structural instance on a block)\n
    if _contains_any(t_norm, ["flowport", "itemflow"]):
        return "individual"
    if _contains_any(t_norm, _TYPE_PART_HINTS) or "part" in label_norm:
        return "individual"
    if _contains_any(t_norm, _TYPE_CLASS_HINTS) or _is_type_definition(xmi_type):
        return "class"
    return "individual"

def _infer_xsd_datatype(type_hint: str) -> URIRef:
    """Infer XSD primitive datatype from UML/SysML value-property type hints."""
    hint = _normalize_token(type_hint)
    if hint in {"int", "integer"}:
        return XSD.integer
    if hint in {"float", "double", "real", "decimal", "number"}:
        return XSD.decimal
    if hint in {"bool", "boolean"}:
        return XSD.boolean
    if hint in {"date"}:
        return XSD.date
    if hint in {"datetime"}:
        return XSD.dateTime
    if hint in {"time"}:
        return XSD.time
    return XSD.string

def _extract_enumeration_literals(props: Dict[str, Any]) -> List[str]:
    """Extract possible enumeration literal names from parsed node properties."""
    candidates: List[str] = []
    literal_keys = ["literals", "ownedLiteral", "values", "members", "enumValues"]
    for key in literal_keys:
        value = props.get(key)
        if not value:
            continue
        if isinstance(value, list):
            candidates.extend(str(item).strip() for item in value if str(item).strip())
            continue
        as_text = str(value)
        parts = [part.strip() for part in as_text.replace(";", ",").split(",")]
        candidates.extend(part for part in parts if part)
    # preserve order, drop duplicates
    seen = set()
    unique: List[str] = []
    for name in candidates:
        if name not in seen:
            seen.add(name)
            unique.append(name)
    return unique

def _add_some_values_from_restriction(
    g: Graph,
    source_uri: URIRef,
    prop_uri: URIRef,
    target_uri: URIRef,
    strict_semantics: bool = True,
) -> None:
    """Encode composition as a someValuesFrom existential restriction."""
    source_class = _resolve_resource_class(g, source_uri)
    target_class = _resolve_resource_class(g, target_uri)
    if strict_semantics and (source_class is None or target_class is None):
        return
    if source_class is None:
        source_class = source_uri
        g.add((source_class, RDF.type, OWL.Class))
    if target_class is None:
        target_class = target_uri
        g.add((target_class, RDF.type, OWL.Class))
    elif (target_class, RDF.type, OWL.Class) not in g:
        g.add((target_class, RDF.type, OWL.Class))
    restriction = BNode()
    g.add((restriction, RDF.type, OWL.Restriction))
    g.add((restriction, OWL.onProperty, prop_uri))
    g.add((restriction, OWL.someValuesFrom, target_class))
    g.add((source_class, RDFS.subClassOf, restriction))


def _add_all_values_from_restriction(
    g: Graph,
    source_uri: URIRef,
    prop_uri: URIRef,
    target_uri: URIRef,
    strict_semantics: bool = True,
) -> None:
    """Encode composition as an allValuesFrom restriction where possible."""
    source_class = _resolve_resource_class(g, source_uri)
    target_class = _resolve_resource_class(g, target_uri)

    if strict_semantics and (source_class is None or target_class is None):
        return

    if source_class is None:
        source_class = source_uri
        g.add((source_class, RDF.type, OWL.Class))

    if target_class is None:
        target_class = target_uri
        g.add((target_class, RDF.type, OWL.Class))
    elif (target_class, RDF.type, OWL.Class) not in g:
        g.add((target_class, RDF.type, OWL.Class))

    restriction = BNode()
    g.add((restriction, RDF.type, OWL.Restriction))
    g.add((restriction, OWL.onProperty, prop_uri))
    g.add((restriction, OWL.allValuesFrom, target_class))
    g.add((source_class, RDFS.subClassOf, restriction))

def _apply_allocation_domain_constraints(
    g: Graph,
    ont_ns: Namespace,
    prop_uri: URIRef,
    source_uri: URIRef,
    target_uri: URIRef,
    strict_semantics: bool = True,
) -> None:
    """Apply explicit domain/range semantics for allocation relations."""
    source_class = _resolve_resource_class(g, source_uri)
    target_class = _resolve_resource_class(g, target_uri)

    if strict_semantics and (source_class is None or target_class is None):
        return

    if source_class is None:
        source_class = ont_ns.AllocationSource
        g.add((source_class, RDF.type, OWL.Class))
        g.add((source_uri, RDF.type, source_class))

    if target_class is None:
        target_class = ont_ns.AllocationTarget
        g.add((target_class, RDF.type, OWL.Class))
        g.add((target_uri, RDF.type, target_class))

    g.add((prop_uri, RDFS.domain, source_class))
    g.add((prop_uri, RDFS.range, target_class))

def _apply_inferred_domain_range(
    g: Graph,
    prop_uri: URIRef,
    source_uri: URIRef,
    target_uri: URIRef,
    strict_semantics: bool = True,
) -> None:
    """Infer property domain/range from class assertions when available."""
    source_class = _resolve_resource_class(g, source_uri)
    target_class = _resolve_resource_class(g, target_uri)
    if strict_semantics:
        if source_class is not None:
            g.add((prop_uri, RDFS.domain, source_class))
        if target_class is not None:
            g.add((prop_uri, RDFS.range, target_class))
        return

    if source_class is None and (source_uri, RDF.type, OWL.ObjectProperty) not in g and (source_uri, RDF.type, OWL.DatatypeProperty) not in g:
        source_class = source_uri
        g.add((source_class, RDF.type, OWL.Class))
    if target_class is None and (target_uri, RDF.type, OWL.ObjectProperty) not in g and (target_uri, RDF.type, OWL.DatatypeProperty) not in g:
        target_class = target_uri
        g.add((target_class, RDF.type, OWL.Class))
    if source_class is not None:
        g.add((prop_uri, RDFS.domain, source_class))
    if target_class is not None:
        g.add((prop_uri, RDFS.range, target_class))

def _resolve_resource_class(g: Graph, resource_uri: URIRef) -> Optional[URIRef]:
    """Resolve the most relevant class for a URI resource."""
    if (resource_uri, RDF.type, OWL.Class) in g:
        return resource_uri

    for obj in g.objects(resource_uri, RDF.type):
        if isinstance(obj, URIRef) and obj not in {OWL.NamedIndividual, OWL.ObjectProperty, OWL.DatatypeProperty, OWL.Class}:
            return obj
    return None

def _is_class_like(g: Graph, resource_uri: URIRef) -> bool:
    """Return True only if the resource is explicitly modeled as a class-like node."""
    if (resource_uri, RDF.type, OWL.Class) in g:
        return True
    resolved = _resolve_resource_class(g, resource_uri)
    return resolved is not None

def _resource_has_semantic_type(g: Graph, resource_uri: URIRef, semantic_class: URIRef) -> bool:
    """Check whether a resource is typed as or subclassed from a semantic class."""
    if (resource_uri, RDF.type, semantic_class) in g:
        return True
    for obj in g.objects(resource_uri, RDF.type):
        if obj == semantic_class:
            return True
        if isinstance(obj, URIRef) and (obj, RDFS.subClassOf, semantic_class) in g:
            return True
    return False

def _is_concept_like(g: Graph, resource_uri: URIRef) -> bool:
    """Return True if a resource is modeled as a SKOS concept or class-backed concept."""
    if (resource_uri, RDF.type, SKOS.Concept) in g or (resource_uri, RDF.type, OWL.Class) in g:
        return True
    for concept_uri in g.objects(resource_uri, None):
        if isinstance(concept_uri, URIRef) and (concept_uri, RDF.type, SKOS.Concept) in g:
            return True
    return False

def _infer_core_semantic_class(
    ont_ns: Namespace,
    xmi_type: str,
    label: str,
    name: str,
    props: Dict[str, Any],
    semantic_kind: str,
) -> URIRef:
    """Resolve the OWL core class for an XMI element in the three-layer model."""
    joined = _normalize_token(f"{xmi_type}{label}{name}{props.get('stereotype', '')}{props.get('appliedStereotype', '')}")
    if "flowport" in joined or "flow_port" in joined:
        return ont_ns.FlowPort
    if "itemflow" in joined or "item_flow" in joined:
        return ont_ns.ItemFlow
    if "interface" in joined or "port" in joined:
        return ont_ns.Interface
    if ("stakeholder" in joined and "need" in joined) or "stakeholderneed" in joined:
        return ont_ns.StakeholderNeed
    if "usecase" in joined or "use case" in str(f"{xmi_type} {label} {name}").lower():
        return ont_ns.UseCase
    if "actor" in joined:
        return ont_ns.Actor
    if "requirement" in joined or joined.startswith("req") or "require" in joined:
        return ont_ns.Requirement
    if "constraintblock" in joined or ("constraint" in joined and "block" in joined):
        return ont_ns.ConstraintBlock
    if "valuetype" in joined or "value_type" in joined:
        return ont_ns.ValueType
    if "signal" in joined:
        return ont_ns.Signal
    if "state" in joined or "region" in joined or "transition" in joined:
        return ont_ns.State
    if "function" in joined or "activity" in joined or "behavior" in joined or "operation" in joined or "interaction" in joined:
        return ont_ns.Function
    if semantic_kind == "stereotype":
        return ont_ns.Stereotype
    return ont_ns.Component

def _core_concept_for_class(ont_ns: Namespace, core_class_uri: URIRef) -> URIRef:
    """Map OWL core classes to their SKOS top concepts."""
    mapping = {
        ont_ns.Component: ont_ns.ComponentConcept,
        ont_ns.Block: ont_ns.ComponentConcept,
        ont_ns.Interface: ont_ns.InterfaceConcept,
        ont_ns.Requirement: ont_ns.RequirementConcept,
        ont_ns.StakeholderNeed: ont_ns.StakeholderNeedConcept,
        ont_ns.Function: ont_ns.FunctionConcept,
        ont_ns.UseCase: ont_ns.UseCaseConcept,
        ont_ns.Stereotype: ont_ns.StereotypeConcept,
        ont_ns.Actor: ont_ns.ActorConcept,
        ont_ns.Activity: ont_ns.ActivityConcept,
        ont_ns.ConstraintBlock: ont_ns.ConstraintBlockConcept,
        ont_ns.ValueType: ont_ns.ValueTypeConcept,
        ont_ns.FlowPort: ont_ns.FlowPortConcept,
        ont_ns.ItemFlow: ont_ns.ItemFlowConcept,
        ont_ns.Signal: ont_ns.SignalConcept,
        ont_ns.State: ont_ns.StateConcept,
    }
    return mapping.get(core_class_uri, ont_ns.ComponentConcept)

def _ensure_vocab_concept(
    g: Graph,
    ont_ns: Namespace,
    raw_id: str,
    display_label: str,
    source_tag: str,
    scheme_uri: URIRef,
    broader_concept_uri: URIRef,
    definition_text: str,
) -> URIRef:
    """Create an explicit SKOS concept for the vocabulary layer."""
    concept_uri = ont_ns[f"{_safe_uri_name(raw_id)}_Concept"]
    if (concept_uri, RDF.type, SKOS.Concept) not in g:
        g.add((concept_uri, RDF.type, SKOS.Concept))
        g.add((concept_uri, RDFS.label, Literal(display_label)))
        g.add((concept_uri, SKOS.prefLabel, Literal(display_label)))
        g.add((concept_uri, SKOS.inScheme, scheme_uri))
        g.add((concept_uri, SKOS.broader, broader_concept_uri))
        g.add((broader_concept_uri, SKOS.narrower, concept_uri))
        g.add((concept_uri, DCTERMS.source, Literal(source_tag)))
        if definition_text:
            g.add((concept_uri, SKOS.definition, Literal(definition_text)))
        for alt_label in _generate_alt_labels(display_label, display_label):
            if alt_label and alt_label != display_label:
                g.add((concept_uri, SKOS.altLabel, Literal(alt_label)))
    return concept_uri

def _ensure_xmi_class(g: Graph, ont_ns: Namespace, raw_id: str, source_tag: str, scheme_uri: URIRef) -> URIRef:
    """Ensure an auto-created XMI target resource exists as a labeled class/concept."""
    class_uri = ont_ns[_safe_uri_name(raw_id)]
    if (class_uri, RDF.type, OWL.Class) not in g:
        label = _humanize_xmi_identifier(raw_id, "class")
        g.add((class_uri, RDF.type, OWL.Class))
        g.add((class_uri, RDFS.subClassOf, ont_ns.Component))
        g.add((class_uri, ont_ns.hasVocabularyTerm, _ensure_vocab_concept(
            g,
            ont_ns,
            raw_id=raw_id,
            display_label=label,
            source_tag=source_tag,
            scheme_uri=scheme_uri,
            broader_concept_uri=ont_ns.ComponentConcept,
            definition_text=f"Auto-created MBSE vocabulary concept for XMI target '{raw_id}'.",
        )))
        g.add((class_uri, RDFS.label, Literal(label)))
        g.add((class_uri, RDFS.comment, Literal(f"Auto-created MBSE class for XMI target '{raw_id}'.")))
        g.add((class_uri, DCTERMS.source, Literal(source_tag)))
    return class_uri

def _owner_class_uri(g: Graph, ont_ns: Namespace, owner_id: str, source_tag: str, scheme_uri: URIRef) -> URIRef:
    """Resolve owner domain for XMI property nodes, defaulting to owl:Thing."""
    if owner_id:
        return _ensure_xmi_class(g, ont_ns, owner_id, source_tag, scheme_uri)
    _ensure_owl_thing_metadata_xmi(g, source_tag)
    return OWL.Thing

def _ensure_owl_thing_metadata_xmi(g: Graph, source_tag: str) -> None:
    """Ensure owl:Thing meets local validation expectations in XMI output."""
    g.add((OWL.Thing, RDF.type, OWL.Class))
    g.add((OWL.Thing, RDFS.label, Literal("Thing")))
    g.add((OWL.Thing, RDFS.comment, Literal("Fallback MBSE class when XMI typing is unresolved.")))
    g.add((OWL.Thing, DCTERMS.source, Literal(source_tag)))

def _humanize_xmi_identifier(raw_id: str, semantic_kind: str) -> str:
    """Create a readable fallback label for anonymous/generated XMI identifiers."""
    prefix = {
        "class": "Class",
        "object_property": "Object Property",
        "datatype_property": "Value Property",
        "individual": "Instance",
    }.get(semantic_kind, "Element")
    suffix = str(raw_id or "unnamed").split("_")[-1] or str(raw_id)
    return f"{prefix} {suffix}"

def _choose_definition_text(props: Dict[str, Any], node_name: str, label: str) -> str:
    """Pick the best available engineering definition text for SKOS definition/comment."""
    for key in ["documentation", "description", "comment", "body", "text", "notes", "ownedComment"]:
        value = props.get(key)
        if value:
            return str(value)
    base = node_name or label or "XMI element"
    return f"Engineering concept extracted from XMI model element '{base}'."

def _generate_alt_labels(primary_name: str, label: str) -> List[str]:
    """Generate practical synonym forms for cross-team naming variation."""
    values: List[str] = []
    for candidate in [primary_name, label]:
        text = str(candidate or "").strip()
        if not text:
            continue
        values.append(text.replace("_", " "))
        values.append(text.replace("-", " "))
        values.append(text.replace("_", "-").replace(" ", "-"))
    seen = set()
    unique: List[str] = []
    for value in values:
        cleaned = " ".join(value.split())
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            unique.append(cleaned)
    return unique

def _add_xmi_provenance(
    g: Graph,
    ontology_uri: URIRef,
    ont_ns: Namespace,
    xmi_file: Path,
    xmi_data: Dict[str, Any],
) -> None:
    """Attach source-level provenance so generated semantics can be audited."""
    source_uri = ont_ns[f"source_{_safe_uri_name(xmi_file.stem)}"]
    g.add((source_uri, RDF.type, PROV.Entity))
    g.add((source_uri, RDFS.label, Literal(xmi_file.name)))
    g.add((source_uri, DCTERMS.identifier, Literal(str(xmi_file))))
    g.add((source_uri, DCTERMS.format, Literal("application/xml")))
    g.add((ontology_uri, PROV.wasDerivedFrom, source_uri))

    try:
        g.add((source_uri, DCTERMS.source, URIRef(xmi_file.resolve().as_uri())))
    except Exception:
        g.add((source_uri, DCTERMS.source, Literal(str(xmi_file))))

    provenance = xmi_data.get("provenance", {})
    xmi_namespace = provenance.get("xmi_namespace")
    if xmi_namespace:
        g.add((source_uri, ont_ns.hasXMINamespace, Literal(xmi_namespace)))
    ns_map = provenance.get("namespaces", {}) or {}
    for prefix, uri in sorted(ns_map.items()):
        if not uri:
            continue
        g.add((source_uri, ont_ns.hasDeclaredNamespace, Literal(f"{prefix}={uri}")))

def _apply_graph_quality_baseline(
    g: Graph,
    ont_ns: Namespace,
    source_tag: str,
    creator_text: str,
    version_text: str,
) -> None:
    """Harmonize metadata so validation sees consistent provenance and documentation."""

    # Mirror dcterms provenance/creator into dc namespace for shape compatibility.
    for subj, _, obj in list(g.triples((None, DCTERMS.source, None))):
        if (subj, DC.source, obj) not in g:
            g.add((subj, DC.source, obj))
    for subj, _, obj in list(g.triples((None, DCTERMS.creator, None))):
        if (subj, DC.creator, obj) not in g:
            g.add((subj, DC.creator, obj))

    # Ensure ontology nodes carry creator/version metadata.
    for ontology_uri in {s for s, _, _ in g.triples((None, RDF.type, OWL.Ontology))}:
        if (ontology_uri, DC.creator, None) not in g:
            g.add((ontology_uri, DC.creator, Literal(creator_text)))
        if (ontology_uri, OWL.versionInfo, None) not in g:
            g.add((ontology_uri, OWL.versionInfo, Literal(version_text)))

    # Ensure core resources have baseline provenance/comment metadata.
    for class_uri in {s for s, _, _ in g.triples((None, RDF.type, OWL.Class))}:
        if not _is_local_resource(class_uri, ont_ns):
            continue
        if (class_uri, DC.source, None) not in g and (class_uri, DCTERMS.source, None) not in g:
            g.add((class_uri, DCTERMS.source, Literal(source_tag)))
            g.add((class_uri, DC.source, Literal(source_tag)))
        if (class_uri, RDFS.comment, None) not in g:
            label = next(g.objects(class_uri, RDFS.label), Literal("Class"))
            g.add((class_uri, RDFS.comment, Literal(f"Generated class resource: {label}.")))

    for prop_uri in {s for s, _, _ in g.triples((None, RDF.type, OWL.ObjectProperty))}:
        if not _is_local_resource(prop_uri, ont_ns):
            continue
        if (prop_uri, DC.source, None) not in g and (prop_uri, DCTERMS.source, None) not in g:
            g.add((prop_uri, DCTERMS.source, Literal(source_tag)))
            g.add((prop_uri, DC.source, Literal(source_tag)))
        if (prop_uri, RDFS.comment, None) not in g:
            label = next(g.objects(prop_uri, RDFS.label), Literal("Object property"))
            g.add((prop_uri, RDFS.comment, Literal(f"Generated object property: {label}.")))

    for prop_uri in {s for s, _, _ in g.triples((None, RDF.type, OWL.DatatypeProperty))}:
        if not _is_local_resource(prop_uri, ont_ns):
            continue
        if (prop_uri, DC.source, None) not in g and (prop_uri, DCTERMS.source, None) not in g:
            g.add((prop_uri, DCTERMS.source, Literal(source_tag)))
            g.add((prop_uri, DC.source, Literal(source_tag)))

def _is_local_resource(uri: URIRef, ont_ns: Namespace) -> bool:
    """Return True for resources in the generated ontology namespace or explicit local fallback nodes."""
    if not isinstance(uri, URIRef):
        return False
    uri_text = str(uri)
    return uri_text.startswith(str(ont_ns)) or uri == OWL.Thing

def _matches_any(value: str, patterns: List[str]) -> bool:
    """Case-insensitive match helper for relation names."""
    value_norm = _normalize_token(value)
    return _contains_any(value_norm, patterns)

def _contains_any(value_norm: str, patterns: List[str]) -> bool:
    return any(_normalize_token(pattern) in value_norm for pattern in patterns)

def _normalize_token(value: str) -> str:
    return str(value or "").lower().replace(" ", "").replace("-", "").replace("_", "")

def _safe_uri_name(name: str) -> str:
    """Convert string to safe URI local name."""
    import re
    # Replace non-alphanumeric characters with underscores
    safe_name = re.sub(r'[^a-zA-Z0-9_]', '_', str(name))
    # Ensure it doesn't start with a number
    if safe_name and safe_name[0].isdigit():
        safe_name = f"_{safe_name}"
    return safe_name or "unnamed"

def _format_property_label(prop_name: str) -> str:
    """Format property name into human-readable label."""
    # Convert UPPERCASE_WITH_UNDERSCORES to Title Case
    words = prop_name.lower().split('_')
    return ' '.join(word.capitalize() for word in words)

# Main execution for standalone use
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Convert XMI file to OWL2/Turtle")
    parser.add_argument("xmi_file", help="Path to XMI file")
    parser.add_argument("output_file", help="Path for output TTL file")
    parser.add_argument("--base-uri", help="Base URI for ontology")
    parser.add_argument("--title", help="Ontology title")
    
    args = parser.parse_args()
    
    success = convert_xmi_to_ttl(
        xmi_path=args.xmi_file,
        output_path=args.output_file,
        base_uri=args.base_uri or "",
        title=args.title or ""
    )
    
    sys.exit(0 if success else 1)
