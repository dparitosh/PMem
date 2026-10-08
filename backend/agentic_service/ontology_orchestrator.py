"""Read-only ontology agent orchestration.

The agents produce evidence and reviewable plans. They never mutate PostgreSQL,
Neo4j, or ontology files. Publication remains owned by the existing
Semantic Bridge and Graph Service approval paths.
"""
from __future__ import annotations

import os
import re
import json
import hashlib
from pathlib import Path
from typing import Any

from rdflib import Graph, RDF, OWL, RDFS, SKOS


ROOT = Path(__file__).resolve().parents[2]


def _allowed_path(value: str) -> Path:
    path = Path(str(value or "")).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    path = path.resolve()
    configured = os.getenv("ONTOLOGY_AGENT_ALLOWED_ROOTS", "data;ontology;backend/test_data;ontology_uploads")
    roots = []
    for item in configured.split(";"):
        if not item.strip():
            continue
        root = Path(item.strip()).expanduser()
        roots.append((root if root.is_absolute() else ROOT / root).resolve())
    if not roots:
        raise ValueError("ONTOLOGY_AGENT_ALLOWED_ROOTS must contain an approved directory")
    if not path.is_file() or not any(path == root or root in path.parents for root in roots):
        raise ValueError("ontology_path must name an existing ontology file under an approved ontology data directory")
    max_bytes = int(os.getenv("ONTOLOGY_AGENT_MAX_BYTES", str(25 * 1024 * 1024)))
    if path.stat().st_size > max_bytes:
        raise ValueError(f"ontology file exceeds ONTOLOGY_AGENT_MAX_BYTES ({max_bytes} bytes)")
    if path.suffix.lower() not in {".owl", ".rdf", ".xml", ".ttl", ".nt", ".n3", ".jsonld"}:
        raise ValueError("ontology_path must use a supported RDF/OWL extension")
    return path


def _load(path: Path) -> Graph:
    from backend.ontology_service.catalog import OntologyCatalog, validate_rdf_input
    limit = int(os.getenv("ONTOLOGY_AGENT_MAX_BYTES", str(25 * 1024 * 1024)))
    if limit <= 0:
        raise ValueError("ONTOLOGY_AGENT_MAX_BYTES must be positive")
    with path.open("rb") as stream:
        content = stream.read(limit + 1)
    if len(content) > limit:
        raise ValueError("Ontology agent input exceeds the configured byte limit")
    if path.suffix.lower() in {".nt", ".n3"}:
        rdf_format = "nt" if path.suffix.lower() == ".nt" else "n3"
    else:
        rdf_format = OntologyCatalog._parse_ontology(content, path.name)["rdf_format"]
        validate_rdf_input(content, rdf_format)
    graph = Graph().parse(data=content, format=rdf_format)
    graph._depo_source_digest = hashlib.sha256(content).hexdigest()
    if not graph:
        raise ValueError("Ontology contains no RDF triples")
    return graph


def inspect_ontology(ontology_path: str) -> dict[str, Any]:
    path = _allowed_path(ontology_path)
    graph = _load(path)
    classes = set(graph.subjects(RDF.type, OWL.Class)) | set(graph.subjects(RDF.type, RDFS.Class))
    object_properties = set(graph.subjects(RDF.type, OWL.ObjectProperty))
    datatype_properties = set(graph.subjects(RDF.type, OWL.DatatypeProperty))
    annotation_properties = set(graph.subjects(RDF.type, OWL.AnnotationProperty))
    individuals = set(graph.subjects(RDF.type, OWL.NamedIndividual))
    typed_terms = [("Class", item) for item in classes]
    typed_terms += [("ObjectProperty", item) for item in object_properties]
    typed_terms += [("DatatypeProperty", item) for item in datatype_properties]
    typed_terms += [("AnnotationProperty", item) for item in annotation_properties]
    typed_terms.sort(key=lambda pair: (pair[0], str(pair[1])))
    term_index = []
    indexed_counts: dict[str, int] = {}
    for kind, term in typed_terms:
        if indexed_counts.get(kind, 0) >= 500:
            continue
        indexed_counts[kind] = indexed_counts.get(kind, 0) + 1
        label = next((str(value) for predicate in (SKOS.prefLabel, RDFS.label)
                      for value in graph.objects(term, predicate) if str(value).strip()), "")
        term_index.append({"kind": kind, "iri": str(term), "label": label,
                           "domains": sorted(str(value) for value in graph.objects(term, RDFS.domain)),
                           "ranges": sorted(str(value) for value in graph.objects(term, RDFS.range))})
    return {
        "path": str(path.relative_to(ROOT)).replace("\\", "/") if ROOT in path.parents else path.name,
        "format": path.suffix.lower().lstrip("."),
        "engine": "rdflib",
        "artifact_digest": graph._depo_source_digest,
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
        "term_index": term_index,
        "term_index_truncated": len(typed_terms) > len(term_index),
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
    if not metadata:
        from backend.ontology_service.catalog import catalog
        metadata = catalog.get(ontology_id)
        if metadata:
            # Resolve only catalog-owned paths, preserving directory containment.
            artifact = Path(str(metadata["artifact_path"])).resolve()
            if not artifact.is_relative_to((catalog.root / ontology_id).resolve()) or not artifact.is_file():
                raise ValueError("Native ontology artifact is missing or outside its catalog directory")
            return str(artifact)
    metadata = metadata or {}
    source = str(metadata.get("file_path") or "")
    # An uploaded XSD or other source artifact may have a generated RDF/OWL
    # representation. Review that representation, not the non-RDF source.
    supported = {".owl", ".rdf", ".xml", ".ttl", ".nt", ".n3", ".jsonld"}
    generated = str(metadata.get("owl_file_path") or "")
    path = generated or (source if Path(source).suffix.lower() in supported else "")
    if not path:
        raise ValueError("The selected ontology has no readable source artifact")
    return path


def _instance_metadata(import_task_id: str | None, supplied: dict[str, Any] | None) -> dict[str, Any]:
    if supplied is not None:
        if not isinstance(supplied, dict):
            raise ValueError("instance_metadata must be an object")
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
    return _review_summary(inspect_ontology(ontology_path))


def _review_summary(summary: dict[str, Any]) -> dict[str, Any]:
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


def plan_bridge(instance_metadata: dict[str, Any], ontology_path: str | None = None,
                ontology_summary: dict[str, Any] | None = None) -> dict[str, Any]:
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
    summary = ontology_summary if ontology_summary is not None else (inspect_ontology(ontology_path) if ontology_path else {})
    kind_for_field = {"entities": "Class", "attributes": "DatatypeProperty",
                      "relationships": "ObjectProperty", "metadata": "AnnotationProperty"}
    normalize = lambda value: re.sub(r"[\W_]+", "", str(value).casefold())
    if sum(plan.values()) > 2000:
        raise ValueError("Bridge planning supports at most 2000 source items; narrow the supplied metadata")
    index = {}
    for term in summary.get("term_index") or []:
        local_name = term.get("iri", "").rsplit("#", 1)[-1].rstrip("/").rsplit("/", 1)[-1]
        if "/" not in term.get("iri", ""):
            local_name = local_name.rsplit(":", 1)[-1]
        for value, evidence in ((term.get("label"), "label"), (local_name, "iri_local_name")):
            key = normalize(value) if value else ""
            if key:
                index.setdefault((term.get("kind"), key), {}).setdefault(term["iri"], (term, evidence))
    from .mapping_validation import check_mapping, source_duplicates
    duplicates = source_duplicates(instance_metadata)
    candidates = []
    items = []
    validations = ["datatype_compatibility", "domain_range_compatibility", "duplicate_check", "scope_check", "human_approval"]
    for field, kind in kind_for_field.items():
        for source in instance_metadata.get(field) or []:
            source_details = source
            if isinstance(source, dict):
                source = source.get("name") or source.get("label") or source.get("source")
            if not isinstance(source, str) or not source.strip():
                raise ValueError(f"instance_metadata.{field} items require a non-empty name")
            source_name = source.strip()
            key = normalize(source_name)
            matches = []
            for term, evidence in index.get((kind, key), {}).values():
                checks = check_mapping(source_details, term, summary, duplicates[field][source_name.casefold()] > 1)
                unresolved = [name for name, status in checks.items() if status in {'not_supplied', 'required', 'reasoning_required'}]
                matches.append({"source": source_name, "source_category": field,
                                "target_iri": term["iri"], "target_type": kind,
                                "evidence": f"exact_normalized_{evidence}",
                                "status": "invalid" if "failed" in checks.values() else "review_required",
                                "validation_checks": checks, "unresolved_checks": unresolved})
            items.append({"source": source_name, "source_category": field,
                          "status": "ambiguous" if len(matches) > 1 else "invalid" if len(matches) == 1 and matches[0]["status"] == "invalid" else "candidate" if matches else "unmatched",
                          "candidate_iris": [row["target_iri"] for row in matches[:3]],
                          "candidate_count": len(matches), "candidates_truncated": len(matches) > 3,
                          "validation_checks": matches[0]["validation_checks"] if len(matches) == 1 else {},
                          "unresolved_checks": matches[0]["unresolved_checks"] if len(matches) == 1 else validations[:],
                          "rationale": "Exact names require semantic and human validation" if matches else
                                       "No exact name found in the inspected term index; further review is required"})
            if len(candidates) < 200:
                candidates.extend(matches[:min(3, 200 - len(candidates))])
    result: dict[str, Any] = {
        "ontology_summary": summary,
        "alignment_plan": plan,
        "alignment_candidates": candidates[:200],
        "alignment_items": items,
        "unmatched_count": sum(item["status"] == "unmatched" for item in items),
        "ambiguous_count": sum(item["status"] == "ambiguous" for item in items),
        "invalid_count": sum(item["status"] == "invalid" for item in items),
        "candidate_limit_reached": sum(item["candidate_count"] for item in items) > len(candidates) or bool(summary.get("term_index_truncated")),
        "required_validations": ["class_existence_check", "property_type_check", "domain_range_check", "approval_required"],
        "status": "review_required" if any(item["status"] != "candidate" for item in items) or summary.get("term_index_truncated") else "ready_for_mapping",
        "publication": "requires_human_approval",
        "llm": _llm_suggestion(plan, instance_metadata, {"terms": summary.get("term_index", [])[:30], "candidates": candidates[:20],
            "artifact_digest": summary.get("artifact_digest"), "term_index_truncated": summary.get("term_index_truncated", False)}),
    }
    return result


def _llm_suggestion(plan: dict[str, int], instance_metadata: dict[str, Any], evidence=None) -> dict[str, Any]:
    """Return an optional bounded suggestion; never treat it as approval."""
    if os.getenv("ONTOLOGY_AGENT_LLM_ENABLED", "false").lower() != "true":
        return {"enabled": False, "mode": "deterministic-evidence-only"}
    try:
        import asyncio
        from .local_llm import review_ontology_evidence
        review = asyncio.run(review_ontology_evidence({**(evidence or {}), 'counts': plan, 'metadata_keys': sorted(instance_metadata)}))
        text = '\n'.join(item['question'] for item in review['questions']) + '\n' + review['limitations']
        return {"enabled": True, "status": "suggestion", "mode": "review-only", "text": text, "review": review}
    except Exception as exc:
        return {"enabled": True, "status": "unavailable", "mode": "review-only", "error_type": type(exc).__name__}


def orchestrate(payload: dict[str, Any]) -> dict[str, Any]:
    workflow_id = str(payload.get("workflow_id") or "ontology_review").strip()
    if workflow_id == "qif_ap242_review":
        return review_qif_ap242(payload)
    if workflow_id not in {"ontology_review", "semantic_bridge_plan"}:
        raise ValueError(f"Unknown ontology agent workflow: {workflow_id}")
    ontology_path = _resolve_ontology_path(str(payload.get("ontology_path") or ""), str(payload.get("ontology_id") or "") or None)
    metadata = _instance_metadata(str(payload.get("import_task_id") or "") or None, payload.get("instance_metadata"))
    summary = inspect_ontology(ontology_path)
    steps = [{"agent": "ontology_intake_agent", "status": "completed", "result": summary}]
    if workflow_id == "ontology_review":
        steps.append({"agent": "ontology_structure_review_agent", "status": "completed", "result": _review_summary(summary)})
    steps.append({"agent": "semantic_bridge_planner_agent", "status": "completed", "result": plan_bridge(metadata, ontology_summary=summary)})
    return {"workflow_id": workflow_id, "steps": steps, "status": "completed", "publication": "requires_human_approval"}


def intake(payload: dict[str, Any]) -> dict[str, Any]:
    path = _resolve_ontology_path(str(payload.get("ontology_path") or ""), str(payload.get("ontology_id") or "") or None)
    return inspect_ontology(path)


def structure_review(payload: dict[str, Any]) -> dict[str, Any]:
    path = _resolve_ontology_path(str(payload.get("ontology_path") or ""), str(payload.get("ontology_id") or "") or None)
    summary = inspect_ontology(path)
    if payload.get('artifact_digest') and payload['artifact_digest'] != summary['artifact_digest']:
        raise ValueError('Ontology artifact changed after intake')
    return _review_summary(summary)


def bridge_plan(payload: dict[str, Any]) -> dict[str, Any]:
    path = _resolve_ontology_path(str(payload.get("ontology_path") or ""), str(payload.get("ontology_id") or "") or None)
    metadata = _instance_metadata(str(payload.get("import_task_id") or "") or None, payload.get("instance_metadata"))
    summary = inspect_ontology(path)
    if payload.get('artifact_digest') and payload['artifact_digest'] != summary['artifact_digest']:
        raise ValueError('Ontology artifact changed after intake')
    return plan_bridge(metadata, ontology_summary=summary)


def review_qif_ap242(payload: dict[str, Any]) -> dict[str, Any]:
    """Produce bounded, read-only candidates from two retained ontology versions."""
    qif_id = str(payload.get("qif_ontology_id") or "").strip()
    target_id = str(payload.get("ap242_ontology_id") or "").strip()
    if not qif_id or not target_id or qif_id == target_id:
        raise ValueError("Two distinct registered QIF and AP242 ontology IDs are required")
    from backend.ontology_service.domain.taxonomy import OntologyTaxonomyService
    for identifier, expected in ((qif_id, "qif"), (target_id, "ap242")):
        meta = OntologyTaxonomyService._resolve_metadata(identifier)
        if meta.get("ontology_id") != identifier:
            raise ValueError("Exact ontology IDs are required; prefix aliases are not accepted")
        markers = " ".join(str(meta.get(key) or "") for key in ("ontology_name", "name", "prefix", "namespace", "source_namespace", "original_filename")).lower()
        if expected not in markers:
            raise ValueError(f"Selected ontology metadata does not identify {expected}; verify its registration")
    source = inspect_ontology(_resolve_ontology_path("", qif_id))
    target = inspect_ontology(_resolve_ontology_path("", target_id))
    fields = {"Class": "entities", "DatatypeProperty": "attributes", "ObjectProperty": "relationships", "AnnotationProperty": "metadata"}
    metadata = {field: [] for field in fields.values()}
    for term in source.get("term_index") or []:
        field = fields.get(term.get("kind"))
        if field:
            metadata[field].append(term.get("label") or term.get("iri", "").rsplit("#", 1)[-1].rsplit("/", 1)[-1])
    if not any(metadata.values()):
        raise ValueError("The QIF ontology contains no inspectable typed terms")
    plan = plan_bridge(metadata, ontology_summary=target)
    source_index = {}
    for term in source.get("term_index") or []:
        field = fields.get(term.get("kind"))
        name = term.get("label") or term.get("iri", "").rsplit("#", 1)[-1].rsplit("/", 1)[-1]
        if field:
            source_index.setdefault((field, name), set()).add(term.get("iri"))
    for candidate in plan.get("alignment_candidates") or []:
        identities = sorted(value for value in source_index.get((candidate["source_category"], candidate["source"]), set()) if value)
        candidate["source_iris"] = identities
        candidate["source_identity_ambiguous"] = len(identities) != 1
        candidate["qif_ontology_id"] = qif_id
        candidate["ap242_ontology_id"] = target_id
    return {"workflow_id": "qif_ap242_review", "qif_ontology_id": qif_id, "ap242_ontology_id": target_id,
        "status": "review_required", "publication": "requires_human_approval",
        "scope": "Schema-name candidates only; no instance links, unit conversions or engineering equivalences established",
        "source_truncated": bool(source.get("term_index_truncated")),
        "checks_required": ["QIF/AP242 schema version", "part revision and instance identity", "PMI and characteristic meaning", "units and coordinates", "datatype and cardinality", "reference and provenance resolution"],
        "steps": [{"agent": "qif_structure_review_agent", "result": _review_summary(source)},
                  {"agent": "ap242_structure_review_agent", "result": _review_summary(target)},
                  {"agent": "qif_ap242_mapping_planner", "result": plan}]}
