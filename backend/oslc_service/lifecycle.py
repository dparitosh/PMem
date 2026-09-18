"""Read-only OSLC extension for durable control-plane evidence.

These are PMem extension resources, not a claim of a standardized OSLC domain.
"""
import hashlib
import json
from urllib.parse import quote
from rdflib import Graph, URIRef, Literal
from rdflib.namespace import RDF, DCTERMS

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from backend.mesh_store import PostgresRegistry
from backend.depo_platform.authorization import graph_read_identity
from backend.Services.oslc_service import OSLCService
from .access import authorize

KINDS = {"job-definitions": "data_job_definitions", "job-runs": "data_job_runs",
         "products": "catalog_products", "ontologies": "ontology_catalog"}
PUBLIC_FIELDS = {"job_id", "run_id", "product_id", "version", "status", "job_type",
                 "ontology_id", "ontology_name", "lifecycle_status", "semantic_completeness", "analytics_profile_artifact_id",
                 "quality_profile", "validation_status", "created_at", "started_at",
                 "finished_at", "updated_at", "event_id", "ceim_version", "mapping_digest"}
router = APIRouter(prefix="/oslc/lifecycle", tags=["OSLC lifecycle extensions"],
                   dependencies=[Depends(graph_read_identity)])


def base():
    if not OSLCService.is_enabled():
        raise HTTPException(404, "OSLC integration is disabled")
    return OSLCService.config().base_url + "/oslc/lifecycle"


@router.get("")
def discovery():
    root = base()
    return {"uri": root, "type": "oslc:ServiceProvider", "read_only": True,
            "queryCapabilities": [{"queryBase": f"{root}/{kind}",
                                   "resourceShape": f"{root}/shapes/{kind}"} for kind in KINDS]}


@router.get("/shapes/{kind}")
def shape(kind: str):
    root = base()
    if kind not in KINDS:
        raise HTTPException(404, "Unknown lifecycle resource")
    return {"uri": f"{root}/shapes/{kind}", "type": "oslc:ResourceShape",
            "describes": [f"{root}/types/{kind}"],
            "properties": [{"name": "identifier", "propertyDefinition": "http://purl.org/dc/terms/identifier",
                            "occurs": "http://open-services.net/ns/core#Exactly-one",
                            "valueType": "http://www.w3.org/2001/XMLSchema#string", "readOnly": True}]
                          + [{"name": field, "propertyDefinition": f"{root}/properties/{field}",
                              "occurs": "http://open-services.net/ns/core#Zero-or-one",
                              "readOnly": True} for field in sorted(PUBLIC_FIELDS)],
            "extension_note": "Evidence is the existing versioned manifest, not flattened ontology facts"}


@router.get("/{kind}/{identifier}")
def resource(kind: str, identifier: str, request: Request, identity: str = Depends(graph_read_identity)):
    root = base()
    if kind not in KINDS:
        raise HTTPException(404, "Unknown lifecycle resource")
    authorize(identity, kind, identifier)
    value = PostgresRegistry(KINDS[kind]).get(identifier)
    if value is None:
        raise HTTPException(404, "Lifecycle resource not found")
    payload = {"uri": f"{root}/{kind}/{quote(identifier, safe='')}",
               "type": f"{root}/types/{kind}", "identifier": identifier,
               "evidence": {key: item for key, item in value.items() if key in PUBLIC_FIELDS and isinstance(item, (str, int, float, bool))}}
    accept = request.headers.get("accept", "application/json")
    media = "application/json"
    if accept in {"text/turtle", "application/rdf+xml", "application/ld+json"}:
        media = accept
        graph = Graph()
        subject = URIRef(payload["uri"])
        graph.add((subject, RDF.type, URIRef(payload["type"])))
        graph.add((subject, DCTERMS.identifier, Literal(identifier)))
        for key, item in payload["evidence"].items():
            graph.add((subject, URIRef(root + "/properties/" + key), Literal(item)))
        body = graph.serialize(format={"text/turtle": "turtle", "application/rdf+xml": "xml",
                                       "application/ld+json": "json-ld"}[media], encoding="utf-8")
    elif accept in {"application/json", "*/*"}:
        body = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    else:
        raise HTTPException(406, "Request application/json, text/turtle, application/rdf+xml or application/ld+json")
    etag = '"' + hashlib.sha256(body).hexdigest() + '"'
    headers = {"ETag": etag, "Cache-Control": "private, no-cache", "Vary": "Accept", "OSLC-Core-Version": "2.0"}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return Response(body, media_type=media, headers=headers)


@router.get("/{kind}")
def query(kind: str, page: int = 1, page_size: int = 50, identity: str = Depends(graph_read_identity)):
    root = base()
    if kind not in KINDS:
        raise HTTPException(404, "Unknown lifecycle resource")
    authorize(identity, kind)
    if not 1 <= page <= 10000 or not 1 <= page_size <= 200:
        raise HTTPException(400, "Invalid paging")
    total, selected = PostgresRegistry(KINDS[kind]).page_keys((page - 1) * page_size, page_size)
    return {"uri": f"{root}/{kind}", "type": "oslc:QueryResult", "oslc:totalCount": total,
            "members": [{"uri": f"{root}/{kind}/{quote(key, safe='')}", "identifier": key} for key in selected],
            "nextPage": f"{root}/{kind}?page={page+1}&page_size={page_size}" if page * page_size < total else None}
