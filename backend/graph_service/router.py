from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from .neo4j_publisher import publisher

router = APIRouter(prefix="/graph", tags=["graph"])


@router.get("/health", summary="Graph service health")
def health() -> dict:
    return {"service": "graph", **publisher.health()}


@router.post("/ontologies/publish", summary="Publish a Turtle ontology as an explorable Neo4j hierarchy")
async def publish_ontology(
    artifact: Annotated[UploadFile, File(description="Turtle ontology artifact")],
    ontology_id: Annotated[str, Form()],
    prefix: Annotated[str, Form()],
) -> dict:
    try:
        return publisher.publish_turtle(content=await artifact.read(), ontology_id=ontology_id, prefix=prefix)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Graph publication failed: {type(exc).__name__}: {exc}") from exc
