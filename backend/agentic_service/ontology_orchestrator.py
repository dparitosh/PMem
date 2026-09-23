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
    max_bytes = int(os.getenv("ONTOLOGY_AGENT_MAX_BYTES", str(25 * 1024 * 1024)))
    if path.stat().st_size > max_bytes:
        raise ValueError(f"ontology file exceeds ONTOLOGY_AGENT_MAX_BYTES ({max_bytes} bytes)")
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
        "path": str(path.relative_to(ROOT)).replace("\\", "/") if ROOT in path.parents else path.name,
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


def _resolve_ontology_path(ontology_path: str, ontology_id: str | None) -> str:
    if ontology_path:
        return ontology_path
    if not ontology_id:
        raise ValueError("ontology_id is required when ontology_path is not supplied")
    from backend.Services.ontology_upload_manager import OntologyUploadManager
    record = OntologyUploadManager.get_ontology(ontology_id)
    metadata = record.get("metadata") if record.get("status") == "success" else None
    path = str((metadata or {}).get("file_path") or "")
    if not path:
        raise ValueError("The selected ontology has no readable source artifact")
    return path


def _instance_metadata(import_task_id: str | None, supplied: dict[str, Any] | None) -> dict[str, Any]:
    if supplied:
        return supplied
    if not import_task_id:
        return {}
    from backend.Services.unified_data_import import UnifiedDataImportService
    task = UnifiedDataImportService._restore_task(import_task_id)
    if not task:
        raise ValueError("The selected import task was not found")
    rows = task.get("parsed_rows") or []
    if not isinstance(rows, list):
        raise ValueError("The selected import task has invalid parsed row data")
    entities: list[str] = []
    attributes: list[str] = []
    relationships: list[str] = []
    for row in rows[:1000]:
        if not isinstance(row, dict):
            continue
        for key, value in row.items():
            key_text = str(key)
            if any(marker in key_text.lower() for marker in ("ref", "href", "parent", "child", "source", "target")):
                relationships.append(key_text)
            elif value not in (None, ""):
                attributes.append(key_text)
        label = row.get("entity_type") or row.get("element_type") or row.get("type") or row.get("name")
        if label:
            entities.append(str(label))
    return {"entities": sorted(set(entities)), "attributes": sorted(set(attributes)), "relationships": sorted(set(relationships)), "metadata": [task.get("filename")] if task.get("filename") else []}


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
    fields = ("entities", "attributes", "relationships", "metadata")
    for field in fields:
        if field in instance_metadata and not isinstance(instance_metadata[field], list):
            raise ValueError(f"instance_metadata.{field} must be an array")
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
    ontology_path = _resolve_ontology_path(str(payload.get("ontology_path") or ""), str(payload.get("ontology_id") or "") or None)
    metadata = _instance_metadata(str(payload.get("import_task_id") or "") or None, payload.get("instance_metadata"))
    steps = [{"agent": "ontology_intake_agent", "status": "completed", "result": inspect_ontology(ontology_path)}]
    if workflow_id == "ontology_review":
        steps.append({"agent": "ontology_structure_review_agent", "status": "completed", "result": review_ontology(ontology_path)})
    steps.append({"agent": "semantic_bridge_planner_agent", "status": "completed", "result": plan_bridge(metadata, ontology_path)})
    return {"workflow_id": workflow_id, "steps": steps, "status": "completed", "publication": "requires_human_approval"}
