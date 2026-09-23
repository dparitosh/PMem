"""Read-only ontology agent orchestration.

The agents produce evidence and reviewable plans. They never mutate PostgreSQL,
Neo4j, or ontology files. Publication remains owned by the existing
Semantic Bridge and Graph Service approval paths.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from rdflib import Graph, RDF, OWL, RDFS


ROOT = Path(__file__).resolve().parents[2]


def _allowed_path(value: str) -> Path:
    path = Path(str(value or "")).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    path = path.resolve()
    configured = os.getenv("ONTOLOGY_AGENT_ALLOWED_ROOTS", "data;ontology;backend/test_data;ontology_uploads")
    roots = []
    for item in configured.split(";"):
        root = Path(item.strip()).expanduser()
        roots.append((root if root.is_absolute() else ROOT / root).resolve())
    if not path.is_file() or not any(path == root or root in path.parents for root in roots):
        raise ValueError("ontology_path must name an existing ontology file under an approved ontology data directory")
    if path.suffix.lower() not in {".owl", ".rdf", ".xml", ".ttl", ".nt", ".n3", ".jsonld"}:
        raise ValueError("ontology_path must use a supported RDF/OWL extension")
    return path


def _load(path: Path) -> Graph:
    graph = Graph()
    graph.parse(path.as_posix())
    return graph


def inspect_ontology(ontology_path: str) -> dict[str, Any]:
    path = _allowed_path(ontology_path)
    graph = _load(path)
    classes = set(graph.subjects(RDF.type, OWL.Class)) | set(graph.subjects(RDF.type, RDFS.Class))
    object_properties = set(graph.subjects(RDF.type, OWL.ObjectProperty))
    datatype_properties = set(graph.subjects(RDF.type, OWL.DatatypeProperty))
    annotation_properties = set(graph.subjects(RDF.type, OWL.AnnotationProperty))
    individuals = set(graph.subjects(RDF.type, OWL.NamedIndividual))
    return {
        "path": str(path),
        "format": path.suffix.lower().lstrip("."),
        "engine": "rdflib",
        "triples": len(graph),
        "classes": len(classes),
        "object_properties": len(object_properties),
        "datatype_properties": len(datatype_properties),
        "annotation_like_properties": len(annotation_properties),
        "individuals": len(individuals),
        "subclass_edges": len(set(graph.triples((None, RDFS.subClassOf, None)))),
        "domain_edges": len(set(graph.triples((None, RDFS.domain, None)))),
        "range_edges": len(set(graph.triples((None, RDFS.range, None)))),
        "ontology_iris": sorted({str(item) for item in graph.subjects(RDF.type, OWL.Ontology)}),
        "warnings": [],
    }


def review_ontology(ontology_path: str) -> dict[str, Any]:
    summary = inspect_ontology(ontology_path)
    issues = []
    if not summary["classes"]:
        issues.append({"severity": "high", "code": "NO_CLASSES", "message": "No OWL classes were detected."})
    if not summary["object_properties"] and not summary["datatype_properties"]:
        issues.append({"severity": "high", "code": "NO_PROPERTIES", "message": "No object or datatype properties were detected."})
    if summary["classes"] and not summary["domain_edges"]:
        issues.append({"severity": "medium", "code": "NO_DOMAIN_EDGES", "message": "No property domain edges were detected."})
    if summary["classes"] and not summary["range_edges"]:
        issues.append({"severity": "medium", "code": "NO_RANGE_EDGES", "message": "No property range edges were detected."})
    if not summary["individuals"]:
        issues.append({"severity": "low", "code": "NO_INDIVIDUALS", "message": "No ontology individuals were detected; this may be valid for a schema-only artifact."})
    return {"summary": summary, "issues": issues, "status": "review_required" if issues else "ready"}


def plan_bridge(instance_metadata: dict[str, Any], ontology_path: str | None = None) -> dict[str, Any]:
    if not isinstance(instance_metadata, dict):
        raise ValueError("instance_metadata must be an object")
    plan = {
        "entity_to_class": len(instance_metadata.get("entities") or []),
        "attribute_to_dataproperty": len(instance_metadata.get("attributes") or []),
        "relationship_to_objectproperty": len(instance_metadata.get("relationships") or []),
        "metadata_to_annotation_or_provenance": len(instance_metadata.get("metadata") or []),
    }
    result: dict[str, Any] = {
        "ontology_summary": inspect_ontology(ontology_path) if ontology_path else {},
        "alignment_plan": plan,
        "required_validations": ["class_existence_check", "property_type_check", "domain_range_check", "approval_required"],
        "status": "ready_for_mapping",
        "llm": _llm_suggestion(plan, instance_metadata),
    }
    return result


def _llm_suggestion(plan: dict[str, int], instance_metadata: dict[str, Any]) -> dict[str, Any]:
    """Return an optional bounded suggestion; never treat it as approval."""
    if os.getenv("ONTOLOGY_AGENT_LLM_ENABLED", "false").lower() != "true":
        return {"enabled": False, "mode": "deterministic-evidence-only"}
    try:
        from backend.core.llm import LLM_AVAILABLE, llm
        if not LLM_AVAILABLE:
            return {"enabled": True, "status": "unavailable", "mode": "review-only"}
        prompt = (
            "You are a review-only ontology assistant. Given these measured mapping counts "
            f"{plan} and instance metadata keys {sorted(instance_metadata)}, provide at most "
            "three concise validation questions. Do not propose writes or approvals."
        )
        response = llm.invoke(prompt)
        content = getattr(response, "content", response)
        if isinstance(content, list):
            content = " ".join(str(item.get("text", item)) if isinstance(item, dict) else str(item) for item in content)
        return {"enabled": True, "status": "suggestion", "mode": "review-only", "text": str(content)[:4000]}
    except Exception:
        return {"enabled": True, "status": "unavailable", "mode": "review-only"}


def orchestrate(payload: dict[str, Any]) -> dict[str, Any]:
    workflow_id = str(payload.get("workflow_id") or "ontology_review").strip()
    if workflow_id not in {"ontology_review", "semantic_bridge_plan"}:
        raise ValueError(f"Unknown ontology agent workflow: {workflow_id}")
    ontology_path = str(payload.get("ontology_path") or "")
    steps = [{"agent": "ontology_intake_agent", "status": "completed", "result": inspect_ontology(ontology_path)}]
    if workflow_id == "ontology_review":
        steps.append({"agent": "ontology_structure_review_agent", "status": "completed", "result": review_ontology(ontology_path)})
    metadata = payload.get("instance_metadata") or {}
    steps.append({"agent": "semantic_bridge_planner_agent", "status": "completed", "result": plan_bridge(metadata, ontology_path)})
    return {"workflow_id": workflow_id, "steps": steps, "status": "completed", "publication": "requires_human_approval"}
