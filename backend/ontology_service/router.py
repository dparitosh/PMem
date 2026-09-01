from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from .catalog import catalog
from .semantica_adapter import semantica

router = APIRouter(prefix="/ontologies", tags=["ontologies"])


@router.get("/health", summary="Ontology service health")
def health() -> dict:
    return {"status": "ok", "service": "ontology", "semantica": semantica.capabilities()}


@router.get("/capabilities", summary="Ontology generation and validation capabilities")
def capabilities() -> dict:
    return semantica.capabilities()


@router.post("/generate", summary="Generate, validate, evaluate and export an ontology using Semantica")
def generate_ontology(payload: dict[str, Any]) -> dict:
    data = payload.get("data") or {"entities": payload.get("entities", []), "relationships": payload.get("relationships", [])}
    result = semantica.generate(
        data=data, name=str(payload.get("name") or "GeneratedOntology"),
        base_uri=str(payload.get("base_uri") or "https://depo.local/ontology/"),
    )
    return {"ontology": result["ontology"], "validation": result["validation"], "evaluation": result["evaluation"],
            "artifacts": {name: content.decode("utf-8") for name, content in result["artifacts"].items()}}


@router.get("", summary="List ontology artifacts registered by this service")
def list_ontologies() -> dict:
    ontologies = catalog.list()
    return {"ontologies": ontologies, "count": len(ontologies)}


@router.get("/{ontology_id}", summary="Read ontology artifact metadata")
def get_ontology(ontology_id: str) -> dict:
    ontology = catalog.get(ontology_id)
    if ontology is None:
        raise HTTPException(status_code=404, detail="Ontology artifact not found")
    return ontology


@router.post("/register", status_code=201, summary="Register an OWL/RDF artifact")
async def register_ontology(
    artifact: Annotated[UploadFile, File(description="TTL, RDF/XML, OWL or JSON-LD ontology artifact")],
    ontology_name: Annotated[str, Form()],
    prefix: Annotated[str, Form()],
    description: Annotated[str, Form()] = "",
    source: Annotated[str, Form()] = "api",
) -> dict:
    try:
        return catalog.register(
            content=await artifact.read(), filename=artifact.filename or "ontology.ttl",
            ontology_name=ontology_name, prefix=prefix, description=description, source=source,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
