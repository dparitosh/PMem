from __future__ import annotations

from collections import Counter
from io import BytesIO
from pathlib import Path
from typing import Any, BinaryIO
import xml.etree.ElementTree as ET
import zipfile

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import DCTERMS, RDF, RDFS, XSD

from ontology_agentic.config import settings

SUPPORTED_REQIF_EXTENSIONS = {".reqif", ".xml", ".reqifz"}
TARGET_REQIF_VERSION = "1.2"
REQIF_SCHEMA_NAMESPACE = "http://www.omg.org/spec/ReqIF/20110401/reqif.xsd"
REQIF_DRIVER_XSD = "https://www.omg.org/spec/ReqIF/20110402/driver.xsd"
REQIF_XSD = "https://www.omg.org/spec/ReqIF/20110401/reqif.xsd"
REQIF_CMOF = "https://www.omg.org/spec/ReqIF/20101201/reqif.cmof"
REQIF_NS = Namespace(f"{REQIF_SCHEMA_NAMESPACE}#")
OSLC_RM = Namespace("http://open-services.net/ns/rm#")
DEPO_REQ = Namespace(f"{settings.depo_namespace_base}reqif#")


def _local_name(tag: str) -> str:
    return str(tag).rsplit("}", 1)[-1] if "}" in str(tag) else str(tag)


def _namespace_uri(tag: str) -> str:
    value = str(tag)
    if value.startswith("{") and "}" in value:
        return value[1:].split("}", 1)[0]
    return ""


def _ensure_reqif_path(path_value: str | Path) -> Path:
    path = Path(path_value)
    if not path.exists():
        raise FileNotFoundError(f"ReqIF file not found: {path}")
    if path.suffix.lower() not in SUPPORTED_REQIF_EXTENSIONS:
        raise ValueError(f"Unsupported ReqIF extension: {path.suffix}")
    return path


def _open_reqif_stream(path: Path) -> tuple[BinaryIO, str]:
    if path.suffix.lower() != ".reqifz":
        return path.open("rb"), path.name

    archive = zipfile.ZipFile(path)
    candidates = [name for name in archive.namelist() if name.lower().endswith((".reqif", ".xml"))]
    if not candidates:
        archive.close()
        raise ValueError(f"ReqIFZ archive does not contain a .reqif or .xml file: {path}")
    member_name = sorted(candidates)[0]
    data = archive.read(member_name)
    archive.close()
    return BytesIO(data), member_name


def _attr(element: ET.Element, name: str) -> str:
    return str(element.attrib.get(name, "") or "").strip()


def _desc_text(element: ET.Element, child_name: str) -> str:
    for child in list(element):
        if _local_name(child.tag) == child_name:
            return "".join(child.itertext()).strip()
    return ""


def _first_ref(element: ET.Element, container_name: str) -> str:
    for child in element.iter():
        if _local_name(child.tag) == container_name:
            for ref in child.iter():
                if _local_name(ref.tag).endswith("-REF") and ref.text:
                    return ref.text.strip()
    return ""


def _attribute_values(element: ET.Element, limit: int = 20) -> list[dict[str, str]]:
    values: list[dict[str, str]] = []
    for child in element.iter():
        name = _local_name(child.tag)
        if not name.startswith("ATTRIBUTE-VALUE"):
            continue
        value = _attr(child, "THE-VALUE") or "".join(child.itertext()).strip()
        definition_ref = _first_ref(child, "DEFINITION")
        if value or definition_ref:
            values.append({"definition_ref": definition_ref, "value": value[:500]})
        if len(values) >= limit:
            break
    return values


def _parse_reqif(path: Path, sample_size: int = 20) -> dict[str, Any]:
    stream, source_member = _open_reqif_stream(path)
    counts: Counter[str] = Counter()
    requirement_samples: list[dict[str, Any]] = []
    relation_samples: list[dict[str, str]] = []
    spec_samples: list[dict[str, str]] = []
    attribute_definitions: Counter[str] = Counter()
    root_name = ""
    namespace_uri = ""

    try:
        for event, elem in ET.iterparse(stream, events=("start", "end")):
            if event == "start" and not root_name:
                root_name = _local_name(elem.tag)
                namespace_uri = _namespace_uri(elem.tag)
                continue
            if event != "end":
                continue
            name = _local_name(elem.tag)
            counts[name] += 1

            if name.startswith("ATTRIBUTE-DEFINITION"):
                attribute_definitions[name] += 1

            if name == "SPEC-OBJECT" and len(requirement_samples) < sample_size:
                requirement_samples.append(
                    {
                        "identifier": _attr(elem, "IDENTIFIER"),
                        "long_name": _attr(elem, "LONG-NAME"),
                        "description": _desc_text(elem, "DESC")[:500],
                        "type_ref": _first_ref(elem, "TYPE"),
                        "attributes": _attribute_values(elem),
                    }
                )
            elif name == "SPEC-RELATION" and len(relation_samples) < sample_size:
                relation_samples.append(
                    {
                        "identifier": _attr(elem, "IDENTIFIER"),
                        "long_name": _attr(elem, "LONG-NAME"),
                        "source_ref": _first_ref(elem, "SOURCE"),
                        "target_ref": _first_ref(elem, "TARGET"),
                        "type_ref": _first_ref(elem, "TYPE"),
                    }
                )
            elif name == "SPECIFICATION" and len(spec_samples) < sample_size:
                spec_samples.append(
                    {
                        "identifier": _attr(elem, "IDENTIFIER"),
                        "long_name": _attr(elem, "LONG-NAME"),
                        "description": _desc_text(elem, "DESC")[:500],
                        "type_ref": _first_ref(elem, "TYPE"),
                    }
                )
    finally:
        stream.close()

    return {
        "path": str(path),
        "source_member": source_member,
        "format": "reqifz" if path.suffix.lower() == ".reqifz" else "reqif",
        "target_reqif_version": TARGET_REQIF_VERSION,
        "schema_profile": "OMG ReqIF 1.2 machine-readable schema family",
        "root_element": root_name,
        "namespace_uri": namespace_uri,
        "schema_urls": {
            "driver_xsd": REQIF_DRIVER_XSD,
            "reqif_xsd": REQIF_XSD,
            "reqif_cmof": REQIF_CMOF,
        },
        "counts": {
            "spec_objects": counts["SPEC-OBJECT"],
            "spec_object_types": counts["SPEC-OBJECT-TYPE"],
            "specifications": counts["SPECIFICATION"],
            "spec_relations": counts["SPEC-RELATION"],
            "spec_relation_types": counts["SPEC-RELATION-TYPE"],
            "attribute_values": sum(count for key, count in counts.items() if key.startswith("ATTRIBUTE-VALUE")),
            "attribute_definitions": sum(attribute_definitions.values()),
        },
        "attribute_definition_types": dict(attribute_definitions),
        "requirement_samples": requirement_samples,
        "relation_samples": relation_samples,
        "specification_samples": spec_samples,
        "status": "parsed",
    }


def inspect_reqif_file(path_value: str | Path, sample_size: int = 20) -> dict[str, Any]:
    path = _ensure_reqif_path(path_value)
    return _parse_reqif(path, sample_size=max(0, min(int(sample_size), 100)))


def export_reqif_to_ttl(
    path_value: str | Path,
    output_path: str | Path | None = None,
    base_uri: str | None = None,
    sample_size: int = 10000,
) -> dict[str, Any]:
    path = _ensure_reqif_path(path_value)
    base_uri = base_uri or settings.default_reqif_base_uri
    summary = _parse_reqif(path, sample_size=max(0, int(sample_size)))
    output = Path(output_path) if output_path else path.with_suffix(".reqif.ttl")
    output.parent.mkdir(parents=True, exist_ok=True)

    graph = Graph()
    graph.bind("reqif", REQIF_NS)
    graph.bind("oslc_rm", OSLC_RM)
    graph.bind("depo_req", DEPO_REQ)
    graph.bind("dcterms", DCTERMS)

    graph.add((DEPO_REQ.Requirement, RDF.type, RDFS.Class))
    graph.add((DEPO_REQ.Requirement, RDFS.subClassOf, OSLC_RM.Requirement))
    graph.add((DEPO_REQ.Specification, RDF.type, RDFS.Class))
    graph.add((DEPO_REQ.SpecRelation, RDF.type, RDFS.Class))
    graph.add((DEPO_REQ.sourceRef, RDF.type, RDF.Property))
    graph.add((DEPO_REQ.targetRef, RDF.type, RDF.Property))
    graph.add((DEPO_REQ.typeRef, RDF.type, RDF.Property))

    for item in summary["requirement_samples"]:
        identifier = item.get("identifier") or item.get("long_name") or f"requirement_{len(graph)}"
        uri = URIRef(base_uri.rstrip("/") + "/requirement/" + str(identifier).replace(" ", "_"))
        graph.add((uri, RDF.type, DEPO_REQ.Requirement))
        graph.add((uri, DCTERMS.identifier, Literal(identifier)))
        if item.get("long_name"):
            graph.add((uri, RDFS.label, Literal(item["long_name"])))
        if item.get("description"):
            graph.add((uri, DCTERMS.description, Literal(item["description"])))
        if item.get("type_ref"):
            graph.add((uri, DEPO_REQ.typeRef, Literal(item["type_ref"])))
        for attr in item.get("attributes", []):
            value = attr.get("value")
            if value:
                graph.add((uri, DEPO_REQ.attributeValue, Literal(value)))

    for item in summary["relation_samples"]:
        identifier = item.get("identifier") or f"relation_{len(graph)}"
        uri = URIRef(base_uri.rstrip("/") + "/relation/" + str(identifier).replace(" ", "_"))
        graph.add((uri, RDF.type, DEPO_REQ.SpecRelation))
        graph.add((uri, DCTERMS.identifier, Literal(identifier)))
        if item.get("source_ref"):
            graph.add((uri, DEPO_REQ.sourceRef, Literal(item["source_ref"])))
        if item.get("target_ref"):
            graph.add((uri, DEPO_REQ.targetRef, Literal(item["target_ref"])))
        if item.get("type_ref"):
            graph.add((uri, DEPO_REQ.typeRef, Literal(item["type_ref"])))

    source_uri = URIRef(base_uri.rstrip("/") + "/source")
    graph.add((source_uri, DCTERMS.source, Literal(str(path))))
    graph.add((source_uri, DEPO_REQ.targetReqifVersion, Literal(TARGET_REQIF_VERSION)))
    graph.add((source_uri, DEPO_REQ.schemaProfile, Literal(summary["schema_profile"])))
    graph.add((source_uri, DEPO_REQ.reqifNamespace, Literal(summary.get("namespace_uri", ""))))
    graph.add((source_uri, DEPO_REQ.specObjectCount, Literal(summary["counts"]["spec_objects"], datatype=XSD.integer)))
    graph.serialize(destination=output, format="turtle")

    return {
        "source_path": str(path),
        "output_path": str(output),
        "target_reqif_version": TARGET_REQIF_VERSION,
        "schema_profile": summary["schema_profile"],
        "summary": summary["counts"],
        "status": "exported",
    }
