from __future__ import annotations

from pathlib import Path
from typing import Any
import re

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import DCTERMS, RDF, RDFS, SKOS, XSD

from ontology_agentic.config import settings

OSLC_RM = Namespace("http://open-services.net/ns/rm#")
REQIF = Namespace("http://www.omg.org/spec/ReqIF/20110401/reqif.xsd#")
SYSML = Namespace("http://www.omg.org/spec/SysML/20181001/SysML#")
AP242 = Namespace("http://www.step-nc.org/ap242#")
PLM = Namespace(f"{settings.depo_namespace_base}plm#")
DEPO_REQ = Namespace(f"{settings.depo_namespace_base}requirements#")

_ID_RE = re.compile(r"\b([A-Z]{2,10}[-_ ]?\d{1,8}(?:[-_.][A-Z0-9]+)*)\b", re.IGNORECASE)
_RELATION_KEYS = {
    "satisfies": "satisfies",
    "satisfied_by": "satisfiedBy",
    "derived_from": "derivedFrom",
    "derives": "derives",
    "refines": "refines",
    "verifies": "verifies",
    "verified_by": "verifiedBy",
    "allocated_to": "allocatedTo",
    "part": "relatedPart",
    "part_id": "relatedPart",
    "function": "relatedFunction",
    "function_id": "relatedFunction",
    "process": "relatedProcess",
    "process_id": "relatedProcess",
    "plm_object": "relatedPlmObject",
    "plm_object_id": "relatedPlmObject",
}


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _first(record: dict[str, Any], keys: list[str]) -> str:
    lowered = {str(k).lower().replace(" ", "_").replace("-", "_"): v for k, v in record.items()}
    for key in keys:
        value = lowered.get(key)
        if value is not None and _clean(value):
            return _clean(value)
    return ""


def _detect_requirement_id(record: dict[str, Any], title: str, text: str) -> str:
    explicit = _first(record, ["requirement_id", "req_id", "id", "identifier", "number", "requirement_number"])
    if explicit:
        return explicit
    for candidate in (title, text):
        match = _ID_RE.search(candidate or "")
        if match:
            return match.group(1).replace(" ", "-").upper()
    return ""


def _split_refs(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        raw_items = value
    else:
        raw_items = re.split(r"[,;|\n]+", str(value))
    refs = []
    seen = set()
    for item in raw_items:
        ref = _clean(item)
        if ref and ref not in seen:
            seen.add(ref)
            refs.append(ref)
    return refs


def _classify_requirement(req: dict[str, Any]) -> str:
    combined = f"{req.get('title', '')} {req.get('text', '')}".lower()
    if any(term in combined for term in ["shall", "must", "required", "requirement"]):
        return "FunctionalRequirement"
    if any(term in combined for term in ["verify", "test", "validate", "inspection"]):
        return "VerificationRequirement"
    if any(term in combined for term in ["dimension", "tolerance", "pmi", "surface", "material"]):
        return "ProductRequirement"
    if any(term in combined for term in ["process", "manufacturing", "operation", "assembly"]):
        return "ManufacturingRequirement"
    return "Requirement"


def normalize_requirement_records(
    records: list[dict[str, Any]],
    source_name: str = "",
    source_type: str = "unstructured",
) -> dict[str, Any]:
    if not isinstance(records, list):
        raise ValueError("records must be a list of objects")

    requirements: list[dict[str, Any]] = []
    relationships: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    duplicate_ids: list[str] = []

    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            continue
        title = _first(record, ["title", "name", "long_name", "summary", "heading"])
        text = _first(record, ["text", "description", "requirement", "statement", "body", "value"])
        req_id = _detect_requirement_id(record, title, text) or f"REQ-AUTO-{index:05d}"
        if req_id in seen_ids:
            duplicate_ids.append(req_id)
        seen_ids.add(req_id)

        normalized = {
            "id": req_id,
            "title": title or req_id,
            "text": text,
            "source_name": source_name,
            "source_type": source_type,
            "status": _first(record, ["status", "state", "lifecycle_state"]),
            "owner": _first(record, ["owner", "author", "responsible", "assigned_to"]),
            "priority": _first(record, ["priority", "severity", "risk"]),
            "verification_method": _first(record, ["verification_method", "verification", "test_method"]),
            "requirement_type": "",
            "raw": record,
        }
        normalized["requirement_type"] = _classify_requirement(normalized)
        requirements.append(normalized)

        lowered = {str(k).lower().replace(" ", "_").replace("-", "_"): v for k, v in record.items()}
        for key, relation_type in _RELATION_KEYS.items():
            for target_ref in _split_refs(lowered.get(key)):
                relationships.append({"source": req_id, "target": target_ref, "type": relation_type})

    return {
        "requirements": requirements,
        "relationships": relationships,
        "quality": {
            "record_count": len(records),
            "requirement_count": len(requirements),
            "relationship_count": len(relationships),
            "duplicate_ids": duplicate_ids,
            "missing_text_count": sum(1 for req in requirements if not req.get("text")),
        },
        "alignment_profile": requirement_alignment_profile(),
        "status": "normalized",
    }


def requirement_alignment_profile() -> dict[str, Any]:
    return {
        "canonical_requirement": {
            "class": "depo_req:Requirement",
            "same_as_or_subclass_of": ["oslc_rm:Requirement", "reqif:SPEC-OBJECT", "sysml:Requirement"],
            "notes": "ReqIF provides interchange structure; OSLC RM provides linked-data interface; SysML/MBSE provides model allocation and verification semantics.",
        },
        "cross_domain_links": [
            {"relation": "satisfies", "target_domain": "MBSE", "meaning": "Function/block/design element satisfies requirement."},
            {"relation": "verifies", "target_domain": "MBSE/Verification", "meaning": "Test, analysis, inspection, or simulation verifies requirement."},
            {"relation": "allocatedTo", "target_domain": "MBSE/AP242/PLM", "meaning": "Requirement allocated to function, part, product feature, or process."},
            {"relation": "relatedPart", "target_domain": "AP242/PLM", "meaning": "Requirement constrains a part, product definition, PMI feature, or BOM item."},
            {"relation": "relatedProcess", "target_domain": "PLM/BOP/MBOM", "meaning": "Requirement impacts manufacturing operation, process plan, or routing."},
            {"relation": "derivedFrom/refines", "target_domain": "Requirements", "meaning": "Requirement decomposition and refinement."},
        ],
        "neo4j_projection": {
            "node_labels": ["Requirement", "OSLCRequirement", "ReqIFSpecObject"],
            "relationship_types": ["SATISFIES", "VERIFIES", "ALLOCATED_TO", "RELATED_PART", "RELATED_PROCESS", "DERIVES", "REFINES"],
            "indexed_keys": ["id", "requirement_id", "source_name"],
        },
    }


def export_requirements_alignment_ttl(payload: dict[str, Any], output_path: str | Path, base_uri: str | None = None) -> dict[str, Any]:
    base_uri = base_uri or settings.default_requirements_base_uri
    requirements = payload.get("requirements", [])
    relationships = payload.get("relationships", [])
    if not isinstance(requirements, list):
        raise ValueError("payload.requirements must be a list")
    if not isinstance(relationships, list):
        raise ValueError("payload.relationships must be a list")

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    graph = Graph()
    graph.bind("depo_req", DEPO_REQ)
    graph.bind("oslc_rm", OSLC_RM)
    graph.bind("reqif", REQIF)
    graph.bind("sysml", SYSML)
    graph.bind("ap242", AP242)
    graph.bind("plm", PLM)
    graph.bind("dcterms", DCTERMS)
    graph.bind("skos", SKOS)

    graph.add((DEPO_REQ.Requirement, RDF.type, RDFS.Class))
    graph.add((DEPO_REQ.Requirement, RDFS.subClassOf, OSLC_RM.Requirement))
    graph.add((DEPO_REQ.Requirement, SKOS.closeMatch, REQIF["SPEC-OBJECT"]))
    graph.add((DEPO_REQ.Requirement, SKOS.closeMatch, SYSML.Requirement))
    graph.add((DEPO_REQ.relatedPart, RDFS.range, AP242.ProductDefinition))
    graph.add((DEPO_REQ.relatedPlmObject, RDFS.range, PLM.BusinessObject))

    for req in requirements:
        req_id = _clean(req.get("id"))
        if not req_id:
            continue
        uri = URIRef(base_uri.rstrip("/") + "/" + req_id.replace(" ", "_"))
        graph.add((uri, RDF.type, DEPO_REQ.Requirement))
        graph.add((uri, RDF.type, OSLC_RM.Requirement))
        graph.add((uri, DCTERMS.identifier, Literal(req_id)))
        graph.add((uri, DEPO_REQ.requirementType, Literal(_clean(req.get("requirement_type")) or "Requirement")))
        for predicate, key in [
            (RDFS.label, "title"),
            (DCTERMS.description, "text"),
            (DEPO_REQ.status, "status"),
            (DEPO_REQ.owner, "owner"),
            (DEPO_REQ.priority, "priority"),
            (DEPO_REQ.verificationMethod, "verification_method"),
            (DEPO_REQ.sourceName, "source_name"),
            (DEPO_REQ.sourceType, "source_type"),
        ]:
            value = _clean(req.get(key))
            if value:
                graph.add((uri, predicate, Literal(value)))

    rel_predicates = {
        "satisfies": DEPO_REQ.satisfies,
        "satisfiedBy": DEPO_REQ.satisfiedBy,
        "derivedFrom": DEPO_REQ.derivedFrom,
        "derives": DEPO_REQ.derives,
        "refines": DEPO_REQ.refines,
        "verifies": DEPO_REQ.verifies,
        "verifiedBy": DEPO_REQ.verifiedBy,
        "allocatedTo": DEPO_REQ.allocatedTo,
        "relatedPart": DEPO_REQ.relatedPart,
        "relatedFunction": DEPO_REQ.relatedFunction,
        "relatedProcess": DEPO_REQ.relatedProcess,
        "relatedPlmObject": DEPO_REQ.relatedPlmObject,
    }
    for rel in relationships:
        source = _clean(rel.get("source"))
        target = _clean(rel.get("target"))
        rel_type = _clean(rel.get("type"))
        if not source or not target:
            continue
        source_uri = URIRef(base_uri.rstrip("/") + "/" + source.replace(" ", "_"))
        target_uri = URIRef(base_uri.rstrip("/") + "/external/" + target.replace(" ", "_"))
        graph.add((source_uri, rel_predicates.get(rel_type, DEPO_REQ.relatedTo), target_uri))

    graph.add((URIRef(base_uri.rstrip("/") + "/alignment-profile"), RDF.type, DEPO_REQ.RequirementAlignmentProfile))
    graph.add((URIRef(base_uri.rstrip("/") + "/alignment-profile"), DEPO_REQ.requirementCount, Literal(len(requirements), datatype=XSD.integer)))
    graph.serialize(destination=output, format="turtle")
    return {"output_path": str(output), "requirement_count": len(requirements), "relationship_count": len(relationships), "status": "exported"}
