"""HTTP browsing and export contracts for registered ingestion artifacts."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
import os
from neo4j import GraphDatabase
from fastapi.responses import Response
from rdflib import Graph

from backend.ontology_service.domain.reasoning import OntologyReasoningService
from backend.ontology_service.domain.taxonomy import OntologyTaxonomyService
from backend.Services.ontology_upload_manager import OntologyUploadManager

router = APIRouter(prefix="/ontology", tags=["ontology-browser"])


@router.get("/{ontology_id}/export")
def export_ontology(ontology_id: str, format: str = "ttl") -> Response:
    formats = {"ttl": ("turtle", "text/turtle"), "rdf": ("xml", "application/rdf+xml"), "owl": ("xml", "application/rdf+xml"), "jsonld": ("json-ld", "application/ld+json")}
    if format not in formats:
        raise HTTPException(422, "Supported export formats: ttl, rdf, owl, jsonld")
    try:
        context = OntologyReasoningService.semantic_context(ontology_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    path = context["file_path"]
    content = path.read_bytes()
    graph = None
    for syntax in (["turtle"] if path.suffix.lower() == ".ttl" else ["xml", "turtle"]):
        try:
            candidate = Graph()
            candidate.parse(data=content, format=syntax)
            graph = candidate
            break
        except Exception:
            continue
    if graph is None:
        raise HTTPException(422, "No valid RDF/OWL artifact is available for export")
    syntax, media_type = formats[format]
    return Response(graph.serialize(format=syntax), media_type=media_type, headers={"Content-Disposition": f'attachment; filename="ontology.{format}"'})


@router.get("/{ontology_id}/reason")
def reasoning(ontology_id: str) -> dict:
    try:
        return OntologyTaxonomyService.get_reasoning(_resolve_ontology_id(ontology_id))
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/{ontology_id}/inference/preview")
def preview_inferences(ontology_id: str, body: dict | None = None) -> dict:
    try:
        return OntologyReasoningService.preview_inferences(_resolve_ontology_id(ontology_id), body or {})
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


def _resolve_ontology_id(ontology_id: str) -> str:
    """Resolve a stable upload id or its human-facing prefix (for example AP242)."""
    requested = str(ontology_id or "").strip()
    if not requested:
        raise ValueError("ontology_id is required")
    direct = OntologyUploadManager.get_ontology(requested)
    if direct.get("status") == "success":
        return requested
    listed = OntologyUploadManager.list_ontologies()
    for entry in listed.get("ontologies") or []:
        if str(entry.get("prefix") or "").strip().lower() == requested.lower():
            return str(entry.get("ontology_id") or requested)
    return requested


def _taxonomy_from_graph(prefix: str) -> dict:
    """Return a read-only taxonomy projection for graph-native ontologies.

    Some baseline ontologies, including AP242, are loaded directly into Neo4j
    rather than through the upload registry. They must remain browseable using
    the same public taxonomy contract as uploaded artifacts.
    """
    with GraphDatabase.driver(os.environ["NEO4J_URI"], auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASS"])) as driver:
        with driver.session(database=os.getenv("NEO4J_DATABASE", "ontology")) as session:
            nodes = session.run(
                "MATCH (n) WHERE (n:OntologyClass OR n:ObjectProperty OR n:DatatypeProperty OR n:OntologyProperty) "
                "AND (toLower(coalesce(n.prefix, n.ontology_prefix, '')) = toLower($prefix) "
                "OR toLower(coalesce(n.source_ontology, '')) STARTS WITH toLower($prefix + '_')) "
                "RETURN elementId(n) AS term_id, coalesce(n.name, n.label, n.uri, n.iri) AS label, "
                "coalesce(n.uri, n.iri, '') AS uri, labels(n) AS labels LIMIT 5000",
                prefix=prefix,
            ).data()
            if not nodes:
                return {"status": "not_found", "ontology_id": prefix, "prefix": prefix, "nodes": [], "edges": [],
                        "summary": {"terms": 0, "taxonomy_links": 0, "triple_count": 0},
                        "diagnostics": [{"severity": "warning", "message": f"No graph taxonomy is loaded for '{prefix}'."}]}
            node_ids = [row["term_id"] for row in nodes]
            edges = session.run(
                "MATCH (source)-[r]->(target) WHERE elementId(source) IN $ids AND elementId(target) IN $ids "
                "RETURN elementId(source) AS source, elementId(target) AS target, type(r) AS type LIMIT 10000",
                ids=node_ids,
            ).data()
    return {
        "status": "success", "ontology_id": prefix, "prefix": prefix, "extraction_source": "neo4j_projection",
        "nodes": [{"term_id": row["term_id"], "label": row.get("label") or row["term_id"], "uri": row.get("uri") or "", "kind": (row.get("labels") or ["OntologyResource"])[0]} for row in nodes],
        "edges": edges,
        "summary": {"terms": len(nodes), "taxonomy_links": len(edges), "triple_count": len(edges)},
        "diagnostics": [],
    }


def _taxonomy_from_dictionary(ontology_id: str) -> dict:
    """Adapt the authoritative dictionary projection into a browse taxonomy."""
    dictionary = data_dictionary(ontology_id)
    payload = dictionary.get("data") or {}
    kinds = (
        ("entities", "Class", "dictionary-class"),
        ("properties", "DatatypeProperty", "dictionary-datatype-property"),
        ("relationships", "ObjectProperty", "dictionary-object-property"),
    )
    nodes = []
    for section, kind, source in kinds:
        for key, item in (payload.get(section) or {}).items():
            item = item or {}
            label = str(item.get("label") or key)
            nodes.append({
                "term_id": str(item.get("iri") or f"{ontology_id}:{label}"),
                "uri": str(item.get("iri") or ""),
                "label": label,
                "definition": str(item.get("definition") or ""),
                "kind": kind,
                "ontology_prefix": dictionary.get("prefix") or ontology_id,
                # UI consumers use these stable type markers to separate OWL
                # classes from datatype and object properties.
                "source": source,
            })
    return {
        "status": "success" if nodes else "not_found", "ontology_id": dictionary.get("ontology_id") or ontology_id,
        "prefix": dictionary.get("prefix") or ontology_id, "extraction_source": "dictionary_projection",
        "nodes": nodes, "edges": [],
        "summary": {"terms": len(nodes), "taxonomy_links": 0, "triple_count": len(nodes)},
        "diagnostics": [] if nodes else [{"severity": "warning", "message": f"No ontology terms are loaded for '{ontology_id}'."}],
    }


@router.get("/{ontology_id}/data-dictionary")
def data_dictionary(ontology_id: str) -> dict:
    try:
        reasoning = OntologyReasoningService.get_reasoning(ontology_id)
    except ValueError:
        # Native standalone-service artifacts do not have the legacy
        # Owlready cache.  Continue to the authoritative Neo4j projection
        # instead of returning a false "not found" response.
        reasoning = {}

    def rows(values: list[dict], kind: str) -> dict:
        return {
            str(item.get("label") or item.get("name") or item.get("term_id") or item.get("iri")): {
                "label": str(item.get("label") or item.get("name") or item.get("term_id") or item.get("iri")),
                "iri": item.get("iri") or item.get("uri") or item.get("term_id") or "",
                "definition": item.get("definition") or item.get("comment") or "",
                "kind": kind,
                "domain": item.get("domain") or [],
                "range": item.get("range") or [],
                "source": "ontology_reasoning",
            }
            for item in values if item.get("label") or item.get("name") or item.get("term_id") or item.get("iri")
        }

    entities = rows(reasoning.get("classes") or [], "Class")
    properties = rows((reasoning.get("datatype_properties") or []) + (reasoning.get("annotation_properties") or []), "DatatypeProperty")
    relationships = rows(reasoning.get("object_properties") or [], "ObjectProperty")
    # Older, already-published ontologies are persisted directly in Neo4j and
    # may not have an Owlready cache.  Preserve their browse experience with a
    # read-only projection of the authoritative graph records.
    if not (entities or properties or relationships):
        with GraphDatabase.driver(os.environ["NEO4J_URI"], auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASS"])) as driver:
            with driver.session(database=os.getenv("NEO4J_DATABASE", "ontology")) as session:
                graph_rows = session.run(
                    "MATCH (n) WHERE (n:OntologyClass OR n:ObjectProperty OR n:DatatypeProperty OR n:OntologyResource) "
                    "AND (n.source_ontology = $id OR n.ontology_id = $id OR n.prefix = $prefix) "
                    "RETURN coalesce(n.name, n.label, n.uri, n.iri) AS label, coalesce(n.uri, n.iri) AS iri, "
                    "n.comment AS definition, n.kind AS resource_kind, labels(n) AS labels LIMIT 10000",
                    id=ontology_id, prefix=ontology_id,
                ).data()
        for item in graph_rows:
            label = str(item.get("label") or item.get("iri") or "")
            if not label:
                continue
            record = {"label": label, "iri": item.get("iri") or "", "definition": item.get("definition") or "", "source": "neo4j"}
            labels = item.get("labels") or []
            if "OntologyClass" in labels or item.get("resource_kind") == "class":
                entities[label] = {**record, "kind": "Class", "domain": [], "range": []}
            elif "ObjectProperty" in labels or item.get("resource_kind") == "property":
                relationships[label] = {**record, "kind": "ObjectProperty", "domain": [], "range": []}
            else:
                properties[label] = {**record, "kind": "DatatypeProperty", "domain": [], "range": []}
    return {"status": "success", "ontology_id": reasoning.get("ontology_id") or ontology_id,
            "prefix": reasoning.get("prefix") or ontology_id, "total_terms": len(entities) + len(properties) + len(relationships),
            "data": {"entities": entities, "properties": properties, "relationships": relationships}}


@router.get("/{ontology_id}/taxonomy")
def taxonomy(ontology_id: str) -> dict:
    resolved_id = _resolve_ontology_id(ontology_id)
    try:
        return OntologyTaxonomyService.get_taxonomy(resolved_id)
    except ValueError:
        # The graph projection is indexed by ontology prefix, whereas the API
        # receives an immutable upload id. Resolve the prefix before falling
        # back so AP242 and other graph-native ontologies remain browseable.
        dictionary_taxonomy = _taxonomy_from_dictionary(resolved_id)
        if dictionary_taxonomy["nodes"]:
            return dictionary_taxonomy
        metadata = OntologyUploadManager.get_ontology(resolved_id).get("metadata") or {}
        return _taxonomy_from_graph(str(metadata.get("prefix") or ontology_id))
