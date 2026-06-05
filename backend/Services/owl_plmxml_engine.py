"""PLMXML -> Turtle conversion.

This engine is dedicated to PLMXML semantic extraction and serialization.
It keeps PLMXML-specific ontology logic separate from the generic XML walker.
"""

from __future__ import annotations

import csv
import json
import os
import re
import shutil
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree as ET

from dotenv import load_dotenv
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import DC, DCTERMS, OWL, RDF, RDFS, XSD

try:
    from .ontology_utils import safe_fragment
except ImportError:
    from ontology_utils import safe_fragment  # type: ignore

try:
    from .plmxml_parser import parse_plmxml_file, _rflp_layer
except ImportError:
    from plmxml_parser import parse_plmxml_file, _rflp_layer  # type: ignore

load_dotenv(Path(__file__).resolve().parent / ".env")

_PLMXML_BASE = os.getenv("IAE_BASE_URI", "http://IAE-depo.com/plmxml-ontology#")
_PLMXML_NS = Namespace(_PLMXML_BASE)

# URI of the shared PLMXML OWL ontology that per-file TTLs import
_PLMXML_ONTO_URI = URIRef("http://IAE-depo.com/plmxml-ontology")
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_REFERENCE_ONTOLOGY_SRC = _PROJECT_ROOT / "ontologies" / "generated"

_TRACE_PROP_MAP: dict[str, str] = {
    "Seg0Realize": "realizes",
    "Seg0Allocate": "allocates",
    "Seg0Satisfy": "satisfies",
    "FND_TraceLink": "tracesTo",
}

_CLASSES = {
    "PLMXMLFile": _PLMXML_NS["PLMXMLFile"],
    "Part": _PLMXML_NS["Part"],
    "ProductView": _PLMXML_NS["ProductView"],
    "ProductInstance": _PLMXML_NS["ProductInstance"],
    "Process": _PLMXML_NS["Process"],
    "ProcessView": _PLMXML_NS["ProcessView"],
    "ProcessInstance": _PLMXML_NS["ProcessInstance"],
    "ChangeNotice": _PLMXML_NS["ChangeNotice"],
    "Revision": _PLMXML_NS["Revision"],
    "Transform": _PLMXML_NS["Transform"],
    "UserData": _PLMXML_NS["UserData"],
    "Document": _PLMXML_NS["Document"],
    "ExternalFile": _PLMXML_NS["ExternalFile"],
    "Relationship": _PLMXML_NS["Relationship"],
    # RFLP / SysML (Teamcenter-specific subType groups)
    "Requirement": _PLMXML_NS["Requirement"],
    "Function": _PLMXML_NS["Function"],
    "LogicalComponent": _PLMXML_NS["LogicalComponent"],
    "PhysicalNode": _PLMXML_NS["PhysicalNode"],
    "GeneralRelation": _PLMXML_NS["GeneralRelation"],
    "Form": _PLMXML_NS["Form"],
    # MBSE Operational Layer (O)
    "OperationalActivity": _PLMXML_NS["OperationalActivity"],
    "Capability": _PLMXML_NS["Capability"],
    "OperationalPerformer": _PLMXML_NS["OperationalPerformer"],
    # MBSE Functional Layer (F)
    "SystemFunction": _PLMXML_NS["SystemFunction"],
    "LogicalFunction": _PLMXML_NS["LogicalFunction"],
    "PhysicalFunction": _PLMXML_NS["PhysicalFunction"],
    "FunctionExchange": _PLMXML_NS["FunctionExchange"],
    # MBSE Logical/Physical Layers (L/P)
    "System": _PLMXML_NS["System"],
    "PhysicalComponent": _PLMXML_NS["PhysicalComponent"],
    "ComponentExchange": _PLMXML_NS["ComponentExchange"],
    "PhysicalLink": _PLMXML_NS["PhysicalLink"],
    # MBSE Generic
    "Package": _PLMXML_NS["Package"],
    "MLModel": _PLMXML_NS["MLModel"],
}

_DATA_PROPS = {
    "schemaVersion": _PLMXML_NS["schemaVersion"],
    "author": _PLMXML_NS["author"],
    "date": _PLMXML_NS["date"],
    "partNumber": _PLMXML_NS["partNumber"],
    "revision": _PLMXML_NS["revision"],
    "description": _PLMXML_NS["description"],
    "type": _PLMXML_NS["type"],
    "structureType": _PLMXML_NS["structureType"],
    "quantity": _PLMXML_NS["quantity"],
    "timeRequired": _PLMXML_NS["timeRequired"],
    "status": _PLMXML_NS["status"],
    "matrix": _PLMXML_NS["matrix"],
    "location": _PLMXML_NS["location"],
    "format": _PLMXML_NS["format"],
    "mimeType": _PLMXML_NS["mimeType"],
    "relationshipType": _PLMXML_NS["relationshipType"],
    "sourceTag": _PLMXML_NS["sourceTag"],
    "rawAttributes": _PLMXML_NS["rawAttributes"],
    "value": _PLMXML_NS["value"],
    # RFLP
    "catalogueId": _PLMXML_NS["catalogueId"],
    "rflpLayer": _PLMXML_NS["rflpLayer"],
    "tcSubType": _PLMXML_NS["tcSubType"],
    "bodyText": _PLMXML_NS["bodyText"],
    "objectString": _PLMXML_NS["objectString"],
    "lastModDate": _PLMXML_NS["lastModDate"],
    "traceSubType": _PLMXML_NS["traceSubType"],
    "tcLabel": _PLMXML_NS["tcLabel"],
    "formAttribute": _PLMXML_NS["formAttribute"],
    "subClass": _PLMXML_NS["subClass"],
}

_OBJECT_PROPS = {
    "contains": _PLMXML_NS["contains"],
    "hasRoot": _PLMXML_NS["hasRoot"],
    "instantiates": _PLMXML_NS["instantiates"],
    "hasChildInstance": _PLMXML_NS["hasChildInstance"],
    "positionedBy": _PLMXML_NS["positionedBy"],
    "referencesProduct": _PLMXML_NS["referencesProduct"],
    "referencesProcess": _PLMXML_NS["referencesProcess"],
    "referencesProductInstance": _PLMXML_NS["referencesProductInstance"],
    "precedes": _PLMXML_NS["precedes"],
    "implementsChange": _PLMXML_NS["implementsChange"],
    "affectedBy": _PLMXML_NS["affectedBy"],
    "hasExternalFile": _PLMXML_NS["hasExternalFile"],
    "hasUserData": _PLMXML_NS["hasUserData"],
    "relatesTo": _PLMXML_NS["relatesTo"],
    "source": _PLMXML_NS["source"],
    "target": _PLMXML_NS["target"],
    # RFLP trace-link object properties
    "realizes": _PLMXML_NS["realizes"],
    "allocates": _PLMXML_NS["allocates"],
    "satisfies": _PLMXML_NS["satisfies"],
    "tracesTo": _PLMXML_NS["tracesTo"],
    "linkedTo": _PLMXML_NS["linkedTo"],
    "hasRequirement": _PLMXML_NS["hasRequirement"],
    "hasRevisionOf": _PLMXML_NS["hasRevisionOf"],
    "hasForm": _PLMXML_NS["hasForm"],
    # MBSE Layer Traceability Properties
    "specifies": _PLMXML_NS["specifies"],
    "specifiedBy": _PLMXML_NS["specifiedBy"],
    "implements": _PLMXML_NS["implements"],
    "implementedBy": _PLMXML_NS["implementedBy"],
    "allocatedBy": _PLMXML_NS["allocatedBy"],
    "satisfiedBy": _PLMXML_NS["satisfiedBy"],
    # MBSE Port/Flow Properties
    "hasInputPort": _PLMXML_NS["hasInputPort"],
    "hasOutputPort": _PLMXML_NS["hasOutputPort"],
    "flows": _PLMXML_NS["flows"],
    "flowsFrom": _PLMXML_NS["flowsFrom"],
    "flowsTo": _PLMXML_NS["flowsTo"],
    "connectsToPort": _PLMXML_NS["connectsToPort"],
    # MBSE Performer/Role Properties
    "performs": _PLMXML_NS["performs"],
    "participatesIn": _PLMXML_NS["participatesIn"],
    "assignedTo": _PLMXML_NS["assignedTo"],
    # MBSE Inheritance/Decomposition Properties
    "inheritsFrom": _PLMXML_NS["inheritsFrom"],
    "refines": _PLMXML_NS["refines"],
    "decomposes": _PLMXML_NS["decomposes"],
    "receives": _PLMXML_NS["receives"],
    "provides": _PLMXML_NS["provides"],
}

_DATA_PROP_DOMAIN_RANGE: dict[str, tuple[str, URIRef]] = {
    "schemaVersion": ("PLMXMLFile", XSD.string),
    "author": ("PLMXMLFile", XSD.string),
    "date": ("PLMXMLFile", XSD.dateTime),
    "partNumber": ("Part", XSD.string),
    "revision": ("Revision", XSD.string),
    "description": ("Part", XSD.string),
    "type": ("Part", XSD.string),
    "structureType": ("ProductView", XSD.string),
    "quantity": ("ProductInstance", XSD.decimal),
    "timeRequired": ("Process", XSD.decimal),
    "status": ("ChangeNotice", XSD.string),
    "matrix": ("Transform", XSD.string),
    "location": ("ExternalFile", XSD.string),
    "format": ("ExternalFile", XSD.string),
    "mimeType": ("ExternalFile", XSD.string),
    "relationshipType": ("Relationship", XSD.string),
    "sourceTag": ("Part", XSD.string),
    "rawAttributes": ("Part", XSD.string),
    "value": ("UserData", XSD.string),
    "catalogueId": ("Requirement", XSD.string),
    "rflpLayer": ("Part", XSD.string),
    "tcSubType": ("Part", XSD.string),
    "bodyText": ("Requirement", XSD.string),
    "objectString": ("Part", XSD.string),
    "lastModDate": ("Part", XSD.string),
    "traceSubType": ("Relationship", XSD.string),
    "tcLabel": ("Part", XSD.string),
    "formAttribute": ("Form", XSD.string),
    "subClass": ("Part", XSD.string),
}

_OBJECT_PROP_DOMAIN_RANGE: dict[str, tuple[str, str]] = {
    "contains": ("PLMXMLFile", "Part"),
    "hasRoot": ("ProductView", "ProductInstance"),
    "instantiates": ("ProductInstance", "Part"),
    "hasChildInstance": ("ProductInstance", "ProductInstance"),
    "positionedBy": ("ProductInstance", "Transform"),
    "referencesProduct": ("ProductView", "Part"),
    "referencesProcess": ("ProcessView", "Process"),
    "referencesProductInstance": ("ProcessInstance", "ProductInstance"),
    "precedes": ("ProcessInstance", "ProcessInstance"),
    "implementsChange": ("Revision", "ChangeNotice"),
    "affectedBy": ("Part", "ChangeNotice"),
    "hasExternalFile": ("Document", "ExternalFile"),
    "hasUserData": ("Part", "UserData"),
    "relatesTo": ("Relationship", "Part"),
    "source": ("Relationship", "Part"),
    "target": ("Relationship", "Part"),
    "realizes": ("Part", "Part"),
    "allocates": ("Part", "Part"),
    "satisfies": ("Part", "Part"),
    "tracesTo": ("Part", "Part"),
    "linkedTo": ("Part", "Part"),
    "hasRequirement": ("Part", "Requirement"),
    "hasRevisionOf": ("Revision", "Part"),
    "hasForm": ("Part", "Form"),
    # MBSE Layer Traceability
    "specifies": ("OperationalActivity", "SystemFunction"),
    "specifiedBy": ("SystemFunction", "OperationalActivity"),
    "implements": ("SystemFunction", "LogicalComponent"),
    "implementedBy": ("LogicalComponent", "SystemFunction"),
    "allocatedBy": ("Part", "Part"),
    "satisfiedBy": ("Part", "Part"),
    # MBSE Ports and Flows
    "hasInputPort": ("SystemFunction", "Part"),
    "hasOutputPort": ("SystemFunction", "Part"),
    "flows": ("FunctionExchange", "SystemFunction"),
    "flowsFrom": ("Part", "Part"),
    "flowsTo": ("Part", "Part"),
    "connectsToPort": ("ComponentExchange", "Part"),
    # MBSE Performer/Assignment
    "performs": ("OperationalPerformer", "OperationalActivity"),
    "participatesIn": ("OperationalPerformer", "OperationalActivity"),
    "assignedTo": ("SystemFunction", "OperationalPerformer"),
    # MBSE Inheritance/Decomposition
    "inheritsFrom": ("Part", "Part"),
    "refines": ("LogicalComponent", "SystemFunction"),
    "decomposes": ("Part", "Part"),
    "receives": ("Part", "Part"),
    "provides": ("Part", "Part"),
}


def _safe_identifier(value: str) -> str:
    return safe_fragment(str(value), allow_dot=True)


def _entity_uri(type_name: str, entity_id: str) -> URIRef:
    return _PLMXML_NS[f"{type_name}_{_safe_identifier(entity_id)}"]


def _string_or_none(value: str) -> Optional[str]:
    value = (value or "").strip()
    return value or None


def _is_plmxml_file(path: Path) -> bool:
    if path.suffix.lower() == ".plmxml":
        return True
    if path.suffix.lower() == ".xml":
        try:
            _, root = next(ET.iterparse(str(path), events=("start",)))
            tag_local = root.tag.split("}", 1)[1] if "}" in root.tag else root.tag
            return tag_local.upper() == "PLMXML" or "plmxml.org" in (root.tag + root.get("xmlns", "")).lower()
        except (ET.ParseError, StopIteration):
            return False
    return False


def _collect_plmxml_files(plmxml_source: str) -> list[Path]:
    source_path = Path(plmxml_source)
    if source_path.is_dir():
        files = sorted(source_path.glob("*.plmxml")) + sorted(source_path.glob("*.xml"))
    elif source_path.is_file():
        files = [source_path]
    else:
        raise FileNotFoundError(f"PLMXML source not found: {plmxml_source}")

    plmxml_files = [file_path for file_path in files if _is_plmxml_file(file_path)]
    if not plmxml_files:
        raise ValueError(f"No PLMXML documents found in: {plmxml_source}")
    return plmxml_files


def _build_header(graph: Graph, title: str, base_uri: str, import_ontology: bool = True) -> None:
    from datetime import datetime, timezone

    ontology_uri = URIRef(base_uri)
    graph.add((ontology_uri, RDF.type, OWL.Ontology))
    graph.add((ontology_uri, RDFS.label, Literal(title, lang="en")))
    graph.add((ontology_uri, RDFS.comment, Literal("PLMXML semantic serialization", lang="en")))
    graph.add((ontology_uri, DC.creator, Literal("GitHub Copilot")))
    graph.add((ontology_uri, DCTERMS.created, Literal(datetime.now(timezone.utc).isoformat(), datatype=XSD.dateTime)))
    graph.add((ontology_uri, DCTERMS.modified, Literal(datetime.now(timezone.utc).isoformat(), datatype=XSD.dateTime)))
    graph.add((ontology_uri, OWL.versionInfo, Literal("2.0", datatype=XSD.string)))
    graph.add((ontology_uri, OWL.imports, URIRef("http://www.w3.org/2004/02/skos/core")))
    graph.add((ontology_uri, OWL.imports, URIRef("http://purl.org/dc/terms/")))
    graph.add((ontology_uri, OWL.imports, URIRef("http://open-services.net/ns/core")))
    if import_ontology:
        # Reference the shared PLMXML OWL ontology so reasoners can resolve
        # all class and property definitions declared there.
        graph.add((ontology_uri, OWL.imports, _PLMXML_ONTO_URI))


def _declare_schema(graph: Graph) -> None:
    for class_name, class_uri in _CLASSES.items():
        graph.add((class_uri, RDF.type, OWL.Class))
        graph.add((class_uri, RDFS.label, Literal(class_name, lang="en")))

    for prop_name, prop_uri in _DATA_PROPS.items():
        graph.add((prop_uri, RDF.type, OWL.DatatypeProperty))
        graph.add((prop_uri, RDFS.label, Literal(prop_name, lang="en")))
        dom_key, rng = _DATA_PROP_DOMAIN_RANGE.get(prop_name, ("Part", XSD.string))
        graph.add((prop_uri, RDFS.domain, _CLASSES.get(dom_key, OWL.Thing)))
        graph.add((prop_uri, RDFS.range, rng))

    for prop_name, prop_uri in _OBJECT_PROPS.items():
        graph.add((prop_uri, RDF.type, OWL.ObjectProperty))
        graph.add((prop_uri, RDFS.label, Literal(prop_name, lang="en")))
        dom_key, rng_key = _OBJECT_PROP_DOMAIN_RANGE.get(prop_name, ("Part", "Part"))
        graph.add((prop_uri, RDFS.domain, _CLASSES.get(dom_key, OWL.Thing)))
        graph.add((prop_uri, RDFS.range, _CLASSES.get(rng_key, OWL.Thing)))


def _add_literal(graph: Graph, subject: URIRef, predicate: URIRef, value: object, datatype: URIRef | None = None) -> None:
    if value is None:
        return
    text = str(value).strip()
    if not text:
        return
    if datatype is None:
        graph.add((subject, predicate, Literal(text)))
    else:
        graph.add((subject, predicate, Literal(text, datatype=datatype)))


def _add_properties_blob(graph: Graph, subject: URIRef, properties: dict[str, str], source_tag: str) -> None:
    if source_tag:
        graph.add((subject, _DATA_PROPS["sourceTag"], Literal(source_tag)))
    if properties:
        graph.add((subject, _DATA_PROPS["rawAttributes"], Literal(json.dumps(properties, sort_keys=True))))


def _link_refs(graph: Graph, subject: URIRef, predicate: URIRef, refs: list[str], uri_map: dict[str, URIRef]) -> None:
    for ref in refs:
        target_uri = uri_map.get(ref)
        if target_uri is not None:
            graph.add((subject, predicate, target_uri))


def _emit_document(graph: Graph, doc, file_path: Path) -> None:
    file_uri = _entity_uri("PLMXMLFile", file_path.name)
    graph.add((file_uri, RDF.type, OWL.NamedIndividual))
    graph.add((file_uri, RDF.type, _CLASSES["PLMXMLFile"]))
    graph.add((file_uri, RDFS.label, Literal(file_path.name)))
    _add_literal(graph, file_uri, _DATA_PROPS["schemaVersion"], doc.schema_version)
    _add_literal(graph, file_uri, _DATA_PROPS["author"], doc.author)
    _add_literal(graph, file_uri, _DATA_PROPS["date"], doc.date)

    part_uris: dict[str, URIRef] = {}
    view_uris: dict[str, URIRef] = {}
    instance_uris: dict[str, URIRef] = {}
    process_uris: dict[str, URIRef] = {}
    process_view_uris: dict[str, URIRef] = {}
    process_instance_uris: dict[str, URIRef] = {}
    change_uris: dict[str, URIRef] = {}
    revision_uris: dict[str, URIRef] = {}
    transform_uris: dict[str, URIRef] = {}
    user_data_uris: dict[str, URIRef] = {}
    document_uris: dict[str, URIRef] = {}
    external_file_uris: dict[str, URIRef] = {}
    generic_uris: dict[str, URIRef] = {}

    for part in doc.parts.values():
        uri = _entity_uri("Part", part.id)
        part_uris[part.id] = uri
        generic_uris[part.id] = uri
        graph.add((uri, RDF.type, OWL.NamedIndividual))
        graph.add((uri, RDF.type, _CLASSES["Part"]))
        graph.add((uri, RDFS.label, Literal(part.name or part.id)))
        _add_literal(graph, uri, _DATA_PROPS["partNumber"], part.part_number)
        _add_literal(graph, uri, _DATA_PROPS["revision"], part.revision)
        _add_literal(graph, uri, _DATA_PROPS["description"], part.description)
        _add_literal(graph, uri, _DATA_PROPS["type"], part.part_type)
        _add_properties_blob(graph, uri, part.properties, part.part_type or "Part")
        graph.add((file_uri, _OBJECT_PROPS["contains"], uri))

    for view in doc.product_views.values():
        uri = _entity_uri("ProductView", view.id)
        view_uris[view.id] = uri
        generic_uris[view.id] = uri
        graph.add((uri, RDF.type, OWL.NamedIndividual))
        graph.add((uri, RDF.type, _CLASSES["ProductView"]))
        graph.add((uri, RDFS.label, Literal(view.name or view.id)))
        _add_literal(graph, uri, _DATA_PROPS["type"], view.view_type)
        _add_literal(graph, uri, _DATA_PROPS["structureType"], view.structure_type)
        _add_properties_blob(graph, uri, view.properties, view.view_type or "ProductView")
        graph.add((file_uri, _OBJECT_PROPS["contains"], uri))

    for instance in doc.product_instances:
        uri = _entity_uri("ProductInstance", instance.id)
        instance_uris[instance.id] = uri
        generic_uris[instance.id] = uri
        graph.add((uri, RDF.type, OWL.NamedIndividual))
        graph.add((uri, RDF.type, _CLASSES["ProductInstance"]))
        graph.add((uri, RDFS.label, Literal(instance.name or instance.id)))
        graph.add((uri, _DATA_PROPS["quantity"], Literal(instance.quantity, datatype=XSD.integer)))
        _add_properties_blob(graph, uri, instance.properties, "ProductInstance")
        graph.add((file_uri, _OBJECT_PROPS["contains"], uri))

    for process in doc.processes.values():
        uri = _entity_uri("Process", process.id)
        process_uris[process.id] = uri
        generic_uris[process.id] = uri
        graph.add((uri, RDF.type, OWL.NamedIndividual))
        graph.add((uri, RDF.type, _CLASSES["Process"]))
        graph.add((uri, RDFS.label, Literal(process.name or process.id)))
        _add_literal(graph, uri, _DATA_PROPS["type"], process.process_type)
        _add_literal(graph, uri, _DATA_PROPS["description"], process.description)
        if process.time_required is not None:
            graph.add((uri, _DATA_PROPS["timeRequired"], Literal(process.time_required, datatype=XSD.decimal)))
        _add_properties_blob(graph, uri, process.properties, process.process_type or "Process")
        graph.add((file_uri, _OBJECT_PROPS["contains"], uri))

    for process_view in doc.process_views.values():
        uri = _entity_uri("ProcessView", process_view.id)
        process_view_uris[process_view.id] = uri
        generic_uris[process_view.id] = uri
        graph.add((uri, RDF.type, OWL.NamedIndividual))
        graph.add((uri, RDF.type, _CLASSES["ProcessView"]))
        graph.add((uri, RDFS.label, Literal(process_view.name or process_view.id)))
        _add_properties_blob(graph, uri, process_view.properties, "ProcessView")
        graph.add((file_uri, _OBJECT_PROPS["contains"], uri))

    for process_instance in doc.process_instances:
        uri = _entity_uri("ProcessInstance", process_instance.id)
        process_instance_uris[process_instance.id] = uri
        generic_uris[process_instance.id] = uri
        graph.add((uri, RDF.type, OWL.NamedIndividual))
        graph.add((uri, RDF.type, _CLASSES["ProcessInstance"]))
        graph.add((uri, RDFS.label, Literal(process_instance.id)))
        _add_properties_blob(graph, uri, process_instance.properties, "ProcessInstance")
        graph.add((file_uri, _OBJECT_PROPS["contains"], uri))

    for change_notice in doc.change_notices.values():
        uri = _entity_uri("ChangeNotice", change_notice.id)
        change_uris[change_notice.id] = uri
        generic_uris[change_notice.id] = uri
        graph.add((uri, RDF.type, OWL.NamedIndividual))
        graph.add((uri, RDF.type, _CLASSES["ChangeNotice"]))
        graph.add((uri, RDFS.label, Literal(change_notice.name or change_notice.id)))
        _add_literal(graph, uri, _DATA_PROPS["type"], change_notice.change_type)
        _add_literal(graph, uri, _DATA_PROPS["status"], change_notice.status)
        _add_literal(graph, uri, _DATA_PROPS["description"], change_notice.description)
        _add_literal(graph, uri, _DATA_PROPS["date"], change_notice.date)
        _add_literal(graph, uri, _DATA_PROPS["author"], change_notice.author)
        _add_properties_blob(graph, uri, change_notice.properties, change_notice.change_type or "ChangeNotice")
        graph.add((file_uri, _OBJECT_PROPS["contains"], uri))

    for revision in doc.revisions.values():
        uri = _entity_uri("Revision", revision.id)
        revision_uris[revision.id] = uri
        generic_uris[revision.id] = uri
        graph.add((uri, RDF.type, OWL.NamedIndividual))
        graph.add((uri, RDF.type, _CLASSES["Revision"]))
        graph.add((uri, RDFS.label, Literal(revision.revision_id or revision.id)))
        _add_literal(graph, uri, _DATA_PROPS["revision"], revision.revision_id)
        _add_literal(graph, uri, _DATA_PROPS["type"], revision.revision_type)
        _add_literal(graph, uri, _DATA_PROPS["description"], revision.description)
        _add_literal(graph, uri, _DATA_PROPS["date"], revision.date)
        _add_properties_blob(graph, uri, revision.properties, revision.revision_type or "Revision")
        graph.add((file_uri, _OBJECT_PROPS["contains"], uri))

    for transform in doc.transforms.values():
        uri = _entity_uri("Transform", transform.id)
        transform_uris[transform.id] = uri
        generic_uris[transform.id] = uri
        graph.add((uri, RDF.type, OWL.NamedIndividual))
        graph.add((uri, RDF.type, _CLASSES["Transform"]))
        graph.add((uri, RDFS.label, Literal(transform.id)))
        if transform.matrix:
            graph.add((uri, _DATA_PROPS["matrix"], Literal(" ".join(str(value) for value in transform.matrix))))
        graph.add((file_uri, _OBJECT_PROPS["contains"], uri))

    for user_data in doc.user_data.values():
        uri = _entity_uri("UserData", user_data.id)
        user_data_uris[user_data.id] = uri
        generic_uris[user_data.id] = uri
        graph.add((uri, RDF.type, OWL.NamedIndividual))
        graph.add((uri, RDF.type, _CLASSES["UserData"]))
        graph.add((uri, RDFS.label, Literal(user_data.title or user_data.id)))
        _add_literal(graph, uri, _DATA_PROPS["type"], user_data.type)
        for key, value in user_data.values.items():
            graph.add((uri, _DATA_PROPS["value"], Literal(f"{key}={value}")))
        graph.add((file_uri, _OBJECT_PROPS["contains"], uri))

    for document in doc.documents.values():
        uri = _entity_uri("Document", document.id)
        document_uris[document.id] = uri
        generic_uris[document.id] = uri
        graph.add((uri, RDF.type, OWL.NamedIndividual))
        graph.add((uri, RDF.type, _CLASSES["Document"]))
        graph.add((uri, RDFS.label, Literal(document.name or document.id)))
        _add_literal(graph, uri, _DATA_PROPS["type"], document.document_type)
        _add_literal(graph, uri, _DATA_PROPS["description"], document.description)
        _add_literal(graph, uri, _DATA_PROPS["revision"], document.revision)
        _add_properties_blob(graph, uri, document.properties, document.document_type or "Document")
        graph.add((file_uri, _OBJECT_PROPS["contains"], uri))

    for external_file in doc.external_files.values():
        uri = _entity_uri("ExternalFile", external_file.id)
        external_file_uris[external_file.id] = uri
        generic_uris[external_file.id] = uri
        graph.add((uri, RDF.type, OWL.NamedIndividual))
        graph.add((uri, RDF.type, _CLASSES["ExternalFile"]))
        graph.add((uri, RDFS.label, Literal(external_file.name or external_file.id)))
        _add_literal(graph, uri, _DATA_PROPS["location"], external_file.location)
        _add_literal(graph, uri, _DATA_PROPS["format"], external_file.format)
        _add_literal(graph, uri, _DATA_PROPS["mimeType"], external_file.mime_type)
        _add_properties_blob(graph, uri, external_file.properties, "ExternalFile")
        graph.add((file_uri, _OBJECT_PROPS["contains"], uri))

    for view in doc.product_views.values():
        view_uri = view_uris[view.id]
        if view.product_ref and view.product_ref in generic_uris:
            graph.add((view_uri, _OBJECT_PROPS["referencesProduct"], generic_uris[view.product_ref]))
        _link_refs(graph, view_uri, _OBJECT_PROPS["hasRoot"], view.root_refs, instance_uris)

    for instance in doc.product_instances:
        instance_uri = instance_uris[instance.id]
        if instance.part_ref and instance.part_ref in part_uris:
            graph.add((instance_uri, _OBJECT_PROPS["instantiates"], part_uris[instance.part_ref]))
        if instance.parent_ref and instance.parent_ref in instance_uris:
            graph.add((instance_uris[instance.parent_ref], _OBJECT_PROPS["hasChildInstance"], instance_uri))
        _link_refs(graph, instance_uri, _OBJECT_PROPS["hasChildInstance"], instance.occurrence_refs, instance_uris)
        if instance.transform_ref and instance.transform_ref in transform_uris:
            graph.add((instance_uri, _OBJECT_PROPS["positionedBy"], transform_uris[instance.transform_ref]))
        _link_refs(graph, instance_uri, _OBJECT_PROPS["hasUserData"], instance.user_data_refs, user_data_uris)

    for process_view in doc.process_views.values():
        process_view_uri = process_view_uris[process_view.id]
        _link_refs(graph, process_view_uri, _OBJECT_PROPS["referencesProcess"], process_view.root_process_refs, process_uris)
        _link_refs(graph, process_view_uri, _OBJECT_PROPS["referencesProduct"], process_view.product_refs, generic_uris)

    for process_instance in doc.process_instances:
        process_instance_uri = process_instance_uris[process_instance.id]
        if process_instance.process_ref and process_instance.process_ref in process_uris:
            graph.add((process_instance_uri, _OBJECT_PROPS["referencesProcess"], process_uris[process_instance.process_ref]))
        _link_refs(graph, process_instance_uri, _OBJECT_PROPS["precedes"], process_instance.predecessor_refs, process_instance_uris)
        _link_refs(graph, process_instance_uri, _OBJECT_PROPS["referencesProductInstance"], process_instance.product_instance_refs, instance_uris)

    for revision in doc.revisions.values():
        revision_uri = revision_uris[revision.id]
        if revision.base_ref and revision.base_ref in generic_uris:
            graph.add((revision_uri, _OBJECT_PROPS["referencesProduct"], generic_uris[revision.base_ref]))
        _link_refs(graph, revision_uri, _OBJECT_PROPS["implementsChange"], revision.change_notice_refs, change_uris)

    for change_notice in doc.change_notices.values():
        change_uri = change_uris[change_notice.id]
        _link_refs(graph, change_uri, _OBJECT_PROPS["affectedBy"], change_notice.affected_items, generic_uris)

    for part in doc.parts.values():
        _link_refs(graph, part_uris[part.id], _OBJECT_PROPS["hasUserData"], part.user_data_refs, user_data_uris)

    for document in doc.documents.values():
        document_uri = document_uris[document.id]
        _link_refs(graph, document_uri, _OBJECT_PROPS["hasExternalFile"], document.external_file_refs, external_file_uris)
        _link_refs(graph, document_uri, _OBJECT_PROPS["hasUserData"], document.user_data_refs, user_data_uris)

    for relationship in doc.relationships:
        relationship_uri = _entity_uri("Relationship", relationship.id)
        graph.add((relationship_uri, RDF.type, OWL.NamedIndividual))
        graph.add((relationship_uri, RDF.type, _CLASSES["Relationship"]))
        graph.add((relationship_uri, RDFS.label, Literal(relationship.id)))
        _add_literal(graph, relationship_uri, _DATA_PROPS["relationshipType"], relationship.relationship_type)
        _add_properties_blob(graph, relationship_uri, relationship.properties, relationship.relationship_type or "Relationship")
        source_uri = generic_uris.get(relationship.source_id)
        target_uri = generic_uris.get(relationship.target_id)
        if source_uri is not None:
            graph.add((relationship_uri, _OBJECT_PROPS["source"], source_uri))
            if target_uri is not None:
                graph.add((source_uri, _OBJECT_PROPS["relatesTo"], target_uri))
        if target_uri is not None:
            graph.add((relationship_uri, _OBJECT_PROPS["target"], target_uri))
        graph.add((file_uri, _OBJECT_PROPS["contains"], relationship_uri))

    # ── Requirements (R-layer) ───────────────────────────────────────────
    req_uris: dict[str, URIRef] = {}
    for req in doc.requirements.values():
        uri = _entity_uri("Requirement", req.id)
        req_uris[req.id] = uri
        generic_uris[req.id] = uri
        graph.add((uri, RDF.type, OWL.NamedIndividual))
        graph.add((uri, RDF.type, _CLASSES["Requirement"]))
        graph.add((uri, RDFS.label, Literal(req.name or req.id)))
        _add_literal(graph, uri, _DATA_PROPS["catalogueId"], req.catalogue_id)
        _add_literal(graph, uri, _DATA_PROPS["revision"], req.revision)
        _add_literal(graph, uri, _DATA_PROPS["bodyText"], req.body_text)
        _add_literal(graph, uri, _DATA_PROPS["objectString"], req.object_string)
        _add_literal(graph, uri, _DATA_PROPS["lastModDate"], req.last_mod_date)
        _add_literal(graph, uri, _DATA_PROPS["rflpLayer"], "R")
        graph.add((file_uri, _OBJECT_PROPS["contains"], uri))

    # ── RFLP Products — Functions (F), Logical (L), Physical (P) ────────
    # Products with Sys0* subTypes are added to parts by the parser; we
    # annotate them here with their RFLP layer.
    for part in doc.parts.values():
        sub_type = part.part_type or ""
        layer = _rflp_layer(sub_type)
        if layer and part.id in part_uris:
            p_uri = part_uris[part.id]
            _add_literal(graph, p_uri, _DATA_PROPS["rflpLayer"], layer)
            _add_literal(graph, p_uri, _DATA_PROPS["tcSubType"], sub_type)
            # Re-type to the appropriate RFLP OWL class
            if layer == "F":
                graph.add((p_uri, RDF.type, _CLASSES["Function"]))
            elif layer == "L":
                graph.add((p_uri, RDF.type, _CLASSES["LogicalComponent"]))
            elif layer == "P":
                if sub_type not in ("Item", "ItemRevision"):
                    graph.add((p_uri, RDF.type, _CLASSES["PhysicalNode"]))

    # ── GeneralRelations (Seg0Realize / Seg0Allocate / Seg0Satisfy / FND_TraceLink) ──
    _TRACE_PROP_MAP = {
        "Seg0Realize":    "realizes",
        "Seg0Allocate":   "allocates",
        "Seg0Satisfy":    "satisfies",
        "FND_TraceLink":  "tracesTo",
    }
    for gr in doc.general_relations:
        gr_uri = _entity_uri("GeneralRelation", gr.id)
        graph.add((gr_uri, RDF.type, OWL.NamedIndividual))
        graph.add((gr_uri, RDF.type, _CLASSES["GeneralRelation"]))
        graph.add((gr_uri, RDFS.label, Literal(gr.id)))
        _add_literal(graph, gr_uri, _DATA_PROPS["traceSubType"], gr.sub_type)
        _add_literal(graph, gr_uri, _DATA_PROPS["tcLabel"], gr.tc_label)
        graph.add((file_uri, _OBJECT_PROPS["contains"], gr_uri))
        # Resolve relatedRefs → typed trace property on the first ref (source),
        # pointing to all subsequent refs (targets)
        resolved = [generic_uris[r] for r in gr.related_refs if r in generic_uris]
        prop_name = _TRACE_PROP_MAP.get(gr.sub_type, "linkedTo")
        prop_uri  = _OBJECT_PROPS.get(prop_name, _PLMXML_NS[prop_name])
        if len(resolved) >= 2:
            source_r = resolved[0]
            for target_r in resolved[1:]:
                graph.add((source_r, prop_uri, target_r))
                graph.add((gr_uri, _OBJECT_PROPS["source"], source_r))
                graph.add((gr_uri, _OBJECT_PROPS["target"], target_r))
        elif len(resolved) == 1:
            graph.add((gr_uri, _OBJECT_PROPS["source"], resolved[0]))

    # ── Forms (ItemRevision Master attributes) ──────────────────────────
    for form in doc.forms.values():
        form_uri = _entity_uri("Form", form.id)
        graph.add((form_uri, RDF.type, OWL.NamedIndividual))
        graph.add((form_uri, RDF.type, _CLASSES["Form"]))
        graph.add((form_uri, RDFS.label, Literal(form.name or form.id)))
        _add_literal(graph, form_uri, _DATA_PROPS["type"], form.sub_type)
        _add_literal(graph, form_uri, _DATA_PROPS["subClass"], form.sub_class)
        _add_literal(graph, form_uri, _DATA_PROPS["description"], form.description)
        for attr_name, attr_val in form.attributes.items():
            if attr_val.strip():
                graph.add((form_uri, _DATA_PROPS["formAttribute"], Literal(f"{attr_name}={attr_val}")))
        graph.add((file_uri, _OBJECT_PROPS["contains"], form_uri))


# ── RFLP layer for a Product subType ────────────────────────────────────────
_RFLP_OWL_CLASS: dict[str, str] = {
    "F": "Function",
    "L": "LogicalComponent",
    "P": "PhysicalNode",
    "R": "Requirement",
}


def _make_graph() -> Graph:
    g = Graph()
    g.bind("plmxml", _PLMXML_NS)
    g.bind("owl", OWL)
    g.bind("rdf", RDF)
    g.bind("rdfs", RDFS)
    g.bind("xsd", XSD)
    g.bind("dc", DC)
    return g


def _write_graph(graph: Graph, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    graph.serialize(destination=str(out_path), format="turtle")
    graph.serialize(destination=str(out_path.with_suffix(".owl")), format="xml")


def copy_plmxml_reference_ontology(output_dir: str | Path) -> dict[str, Path]:
    """Copy shared PLMXML ontology artifacts beside generated individual TTLs.

    This creates a reusable reference package for external tools/reasoners:
      - plmxml_ontology.ttl
      - plmxml_ontology.owl
      - plmxml_shapes.ttl (if present)
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    copied: dict[str, Path] = {}
    ttl_src = _REFERENCE_ONTOLOGY_SRC / "plmxml_ontology.ttl"
    if ttl_src.exists():
        ttl_dst = out_dir / "plmxml_ontology.ttl"
        shutil.copyfile(ttl_src, ttl_dst)
        copied["ontology_ttl"] = ttl_dst

        # Keep an RDF/XML variant for tools preferring .owl serialization.
        g = Graph()
        g.parse(str(ttl_dst), format="turtle")
        owl_dst = out_dir / "plmxml_ontology.owl"
        g.serialize(destination=str(owl_dst), format="xml")
        copied["ontology_owl"] = owl_dst

    shapes_src = _REFERENCE_ONTOLOGY_SRC / "plmxml_shapes.ttl"
    if shapes_src.exists():
        shapes_dst = out_dir / "plmxml_shapes.ttl"
        shutil.copyfile(shapes_src, shapes_dst)
        copied["shapes_ttl"] = shapes_dst

    model_ttl_src = _REFERENCE_ONTOLOGY_SRC / "plmxml_generated_model.ttl"
    if model_ttl_src.exists():
        model_ttl_dst = out_dir / "plmxml_generated_model.ttl"
        shutil.copyfile(model_ttl_src, model_ttl_dst)
        copied["generated_model_ttl"] = model_ttl_dst

    model_owl_src = _REFERENCE_ONTOLOGY_SRC / "plmxml_generated_model.owl"
    if model_owl_src.exists():
        model_owl_dst = out_dir / "plmxml_generated_model.owl"
        shutil.copyfile(model_owl_src, model_owl_dst)
        copied["generated_model_owl"] = model_owl_dst

    alignment_ttl_src = _REFERENCE_ONTOLOGY_SRC / "plmxml_alignment.ttl"
    if alignment_ttl_src.exists():
        alignment_ttl_dst = out_dir / "plmxml_alignment.ttl"
        shutil.copyfile(alignment_ttl_src, alignment_ttl_dst)
        copied["alignment_ttl"] = alignment_ttl_dst

    alignment_owl_src = _REFERENCE_ONTOLOGY_SRC / "plmxml_alignment.owl"
    if alignment_owl_src.exists():
        alignment_owl_dst = out_dir / "plmxml_alignment.owl"
        shutil.copyfile(alignment_owl_src, alignment_owl_dst)
        copied["alignment_owl"] = alignment_owl_dst

    return copied


def convert_plmxml_file_to_ttl(
    plmxml_file: str | Path,
    output_dir: str | Path,
    base_uri: str = "",
    title: str = "",
) -> Path:
    """Convert a **single** PLMXML file to its own TTL/OWL pair.

    Output filename mirrors the input stem:  ``input.xml`` → ``input.ttl`` + ``input.owl``
    """
    file_path = Path(plmxml_file)
    out_dir = Path(output_dir)

    if not base_uri:
        root_base = os.getenv("ONTO_BASE_URI_ROOT", "http://IAE-depo.com/ontology").rstrip("#/")
        base_uri = f"{root_base}/{re.sub(r'[^A-Za-z0-9_]', '_', file_path.stem)}#"
    title = title or file_path.stem

    graph = _make_graph()
    _build_header(graph, title, base_uri, import_ontology=True)
    # Schema declarations (classes/properties) live in the imported ontology;
    # individual per-file graphs contain only named individuals.

    doc = parse_plmxml_file(file_path)
    _emit_document(graph, doc, file_path)

    out_path = out_dir / (file_path.stem + ".ttl")
    _write_graph(graph, out_path)
    return out_path


def convert_plmxml_folder_per_file(
    plmxml_source: str | Path,
    output_dir: str | Path,
    base_uri: str = "",
    copy_reference_ontology: bool = True,
) -> list[Path]:
    """Convert every PLMXML file in *plmxml_source* to a **separate** TTL/OWL pair.

    Returns the list of written TTL paths.
    """
    plmxml_files = _collect_plmxml_files(str(plmxml_source))
    out_dir = Path(output_dir)
    written: list[Path] = []
    for file_path in plmxml_files:
        out_path = convert_plmxml_file_to_ttl(file_path, out_dir, base_uri=base_uri)
        print(f"  TTL: {out_path.name}")
        written.append(out_path)

    if copy_reference_ontology:
        copied = copy_plmxml_reference_ontology(out_dir)
        if copied.get("ontology_ttl"):
            print(f"  REF: {copied['ontology_ttl'].name}")
        if copied.get("ontology_owl"):
            print(f"  REF: {copied['ontology_owl'].name}")
        if copied.get("shapes_ttl"):
            print(f"  REF: {copied['shapes_ttl'].name}")
        if copied.get("generated_model_ttl"):
            print(f"  REF: {copied['generated_model_ttl'].name}")
        if copied.get("generated_model_owl"):
            print(f"  REF: {copied['generated_model_owl'].name}")
        if copied.get("alignment_ttl"):
            print(f"  REF: {copied['alignment_ttl'].name}")
        if copied.get("alignment_owl"):
            print(f"  REF: {copied['alignment_owl'].name}")

    return written


# ── Legacy single-output converter (kept for backward compatibility) ─────────
def convert_plmxml_to_ttl(
    plmxml_source: str,
    output_ttl: str,
    base_uri: str = "",
    prefix: str = "",
    title: str = "",
) -> Path:
    """Merge all PLMXML files in *plmxml_source* into one combined TTL.

    For per-file output use ``convert_plmxml_folder_per_file``.
    """
    source_path = Path(plmxml_source)
    plmxml_files = _collect_plmxml_files(plmxml_source)

    if not base_uri:
        root = os.getenv("ONTO_BASE_URI_ROOT", "http://IAE-depo.com/ontology").rstrip("#/")
        base_uri = f"{root}/{re.sub(r'[^A-Za-z0-9_]', '_', source_path.stem)}#"
    if not prefix:
        raw_prefix = re.sub(r"[^A-Za-z0-9_]", "_", source_path.stem.lower()).strip("_") or "plmxml"
        prefix = raw_prefix[:32]
    title = title or os.getenv("ONTO_TITLE", "PLMXML Ontology")

    graph = _make_graph()
    graph.bind(prefix, _PLMXML_NS)
    # Merged graph is self-contained: include inline schema + imports reference.
    _build_header(graph, title, base_uri, import_ontology=True)
    _declare_schema(graph)

    for file_path in plmxml_files:
        doc = parse_plmxml_file(file_path)
        _emit_document(graph, doc, file_path)

    out_path = Path(output_ttl)
    _write_graph(graph, out_path)
    return out_path


# ── CSV export ───────────────────────────────────────────────────────────────

def _doc_to_csv_rows(doc, file_path: Path) -> list[dict]:
    """Flatten one parsed PlmxmlDocument into a list of context-aware CSV rows.

    Header columns (metadata):  source_file, schema_version, author, date
    Data columns vary by entity_type but always include:
        entity_type, rflp_layer, tc_sub_type, id, name, revision,
        description, part_number, catalogue_id, body_text,
        object_string, last_mod_date, quantity, time_required,
        status, location, trace_sub_type, related_refs,
        master_ref, dataset_ref, form_attributes, raw_attributes
    """
    meta = {
        "source_file":     file_path.name,
        "schema_version":  doc.schema_version,
        "author":          doc.author,
        "date":            doc.date,
    }

    rows: list[dict] = []

    def _row(entity_type: str, rflp: str, tc_sub: str, obj_id: str,
             name: str = "", **extra) -> dict:
        base = dict(meta)
        base.update({
            "entity_type": entity_type,
            "rflp_layer":  rflp,
            "tc_sub_type": tc_sub,
            "id":          obj_id,
            "name":        name,
        })
        base.update(extra)
        return base

    for p in doc.parts.values():
        sub = p.part_type or ""
        rows.append(_row(
            "Part", _rflp_layer(sub), sub, p.id, p.name,
            revision=p.revision, description=p.description,
            part_number=p.part_number, master_ref=p.master_ref,
            raw_attributes=json.dumps(p.properties, separators=(",", ":")),
        ))

    for v in doc.product_views.values():
        rows.append(_row(
            "ProductView", "", v.view_type, v.id, v.name,
            structure_type=v.structure_type,
        ))

    for inst in doc.product_instances:
        rows.append(_row(
            "ProductInstance", "", "", inst.id, inst.name,
            quantity=inst.quantity, master_ref=inst.part_ref,
        ))

    for proc in doc.processes.values():
        rows.append(_row(
            "Process", "F", proc.process_type, proc.id, proc.name,
            description=proc.description, time_required=proc.time_required or "",
        ))

    for cn in doc.change_notices.values():
        rows.append(_row(
            "ChangeNotice", "", cn.change_type, cn.id, cn.name,
            status=cn.status, description=cn.description,
            date=cn.date, author=cn.author,
        ))

    for req in doc.requirements.values():
        rows.append(_row(
            "Requirement", "R", "Requirement", req.id, req.name,
            catalogue_id=req.catalogue_id, revision=req.revision,
            body_text=req.body_text, object_string=req.object_string,
            last_mod_date=req.last_mod_date, dataset_ref=req.dataset_ref,
        ))

    for gr in doc.general_relations:
        rel_predicate = _TRACE_PROP_MAP.get(gr.sub_type, "linkedTo")
        rows.append(_row(
            "GeneralRelation", "", gr.sub_type, gr.id, "",
            trace_sub_type=gr.sub_type, tc_label=gr.tc_label,
            related_refs=" ".join(gr.related_refs),
            relation_predicate=rel_predicate,
        ))

        # Add one row per semantic edge for explicit relationship context.
        if len(gr.related_refs) >= 2:
            source_id = gr.related_refs[0]
            for target_id in gr.related_refs[1:]:
                rows.append(_row(
                    "GeneralRelationEdge", "", gr.sub_type, gr.id, "",
                    trace_sub_type=gr.sub_type,
                    relation_predicate=rel_predicate,
                    relation_source_id=source_id,
                    relation_target_id=target_id,
                ))

    for form in doc.forms.values():
        rows.append(_row(
            "Form", "", form.sub_type, form.id, form.name,
            description=form.description, sub_class=form.sub_class,
            form_attributes=json.dumps(form.attributes, separators=(",", ":")),
        ))

    for ef in doc.external_files.values():
        rows.append(_row(
            "ExternalFile", "", "", ef.id, ef.name,
            location=ef.location, format=ef.format, mime_type=ef.mime_type,
        ))

    for doc_item in doc.documents.values():
        rows.append(_row(
            "Document", "", doc_item.document_type, doc_item.id, doc_item.name,
            revision=doc_item.revision, description=doc_item.description,
        ))

    return rows


_CSV_FIELDNAMES = [
    "source_file", "schema_version", "author", "date",
    "entity_type", "rflp_layer", "tc_sub_type", "id", "name",
    "revision", "description", "part_number", "catalogue_id",
    "body_text", "object_string", "last_mod_date", "quantity",
    "time_required", "status", "location", "format", "mime_type",
    "trace_sub_type", "tc_label", "related_refs",
    "relation_predicate", "relation_source_id", "relation_target_id",
    "master_ref", "dataset_ref", "structure_type", "sub_class",
    "form_attributes", "raw_attributes",
]


def export_plmxml_to_csv(
    plmxml_source: str | Path,
    output_csv: str | Path,
) -> Path:
    """Parse all PLMXML files in *plmxml_source* and write a single flat CSV.

    Header row contains metadata + data column names.
    Each data row represents one entity with its RFLP context.
    """
    plmxml_files = _collect_plmxml_files(str(plmxml_source))
    out_path = Path(output_csv)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    all_rows: list[dict] = []
    for file_path in plmxml_files:
        doc = parse_plmxml_file(file_path)
        all_rows.extend(_doc_to_csv_rows(doc, file_path))

    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=_CSV_FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(all_rows)

    return out_path


def export_plmxml_file_to_csv(
    plmxml_file: str | Path,
    output_csv: str | Path,
) -> Path:
    """Parse a **single** PLMXML file and write its entities to a CSV."""
    file_path = Path(plmxml_file)
    doc = parse_plmxml_file(file_path)
    rows = _doc_to_csv_rows(doc, file_path)

    out_path = Path(output_csv)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=_CSV_FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return out_path


def export_plmxml_folder_per_file_csv(
    plmxml_source: str | Path,
    output_dir: str | Path,
) -> list[Path]:
    """Export one contextual CSV per PLMXML input file.

    Output filename mirrors each source stem: input.xml -> input.csv
    """
    plmxml_files = _collect_plmxml_files(str(plmxml_source))
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for file_path in plmxml_files:
        out_csv = out_dir / f"{file_path.stem}.csv"
        export_plmxml_file_to_csv(file_path, out_csv)
        print(f"  CSV: {out_csv.name}")
        written.append(out_csv)
    return written


__all__ = [
    "convert_plmxml_to_ttl",
    "convert_plmxml_file_to_ttl",
    "convert_plmxml_folder_per_file",
    "export_plmxml_to_csv",
    "export_plmxml_file_to_csv",
    "export_plmxml_folder_per_file_csv",
    "copy_plmxml_reference_ontology",
    "_is_plmxml_file",
]
