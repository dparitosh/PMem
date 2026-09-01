"""Compatibility-first ingestion boundary.

The existing SPA contract remains `/api/v1/ingest-data`; implementation moves
behind this router before parsers and graph writes are extracted in turn.
"""
from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from backend.data_ingestion import (  # temporary adapter: parser extraction is phase two
    _MAX_IMPORT_ROWS,
    _MAX_UPLOAD_BYTES,
    create_constraint_query,
    create_index_query,
    create_node_import_query,
    create_relationship_import_query,
    load_file_from_bytes,
)
from backend.core.graph import query_with_timeout
from .profiles import profiles
import json
import pandas as pd
from defusedxml import ElementTree as ET

router = APIRouter(tags=["ingestion"])


@router.get("/ingestion/health")
def health() -> dict:
    return {"status": "ok", "service": "ingestion", "contract": "v1"}


@router.post("/source-profiles/inspect", summary="Inspect a schema or sample file for profile creation")
async def inspect_source_profile(file: UploadFile = File(...)) -> dict:
    try:
        return profiles.inspect(filename=file.filename or "source", content=await file.read())
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Source inspection failed: {exc}") from exc


@router.get("/source-profiles", summary="List reusable source profiles")
def list_source_profiles() -> dict:
    entries = profiles.list()
    return {"profiles": entries, "count": len(entries)}


@router.post("/source-profiles", summary="Create or version a declarative source profile")
def save_source_profile(profile: dict) -> dict:
    try:
        return profiles.save(profile)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/source-profiles/{profile_id}/normalize", summary="Normalize one source record for the ontology service")
def normalize_source_record(profile_id: str, record: dict) -> dict:
    try:
        return profiles.normalize(profile=profiles.get(profile_id), record=record)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/source-profiles/{profile_id}/execute", summary="Normalize a JSON, JSON-LD, or XML batch with a reusable profile")
async def execute_source_profile(profile_id: str, file: UploadFile = File(...)) -> dict:
    """Produce the canonical entity payload consumed by the ontology service.

    This endpoint deliberately normalizes only; persistence remains an explicit
    downstream ontology/graph operation so uploads cannot mutate the graph by
    surprise.
    """
    try:
        content = await file.read()
        if len(content) > _MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="Upload exceeds the 25 MiB ingestion limit")
        return profiles.normalize_batch(
            profile=profiles.get(profile_id), filename=file.filename or "source", content=content,
        )
    except HTTPException:
        raise
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError, ET.ParseError) as exc:
        raise HTTPException(status_code=422, detail=f"Profile execution failed: {exc}") from exc


@router.post("/ingest-data", summary="Ingest tabular data through the ingestion service")
async def ingest_data(
    file: UploadFile = File(...), nodeDefinitions: str = Form(...), relationshipDefinitions: str = Form(...),
    indexes: str = Form(...), constraints: str = Form(...),
) -> dict:
    try:
        node_defs, rel_defs, index_defs, constraint_defs = [json.loads(item) for item in (nodeDefinitions, relationshipDefinitions, indexes, constraints)]
        if not all(isinstance(item, list) for item in (node_defs, rel_defs, index_defs, constraint_defs)):
            raise ValueError("All ingestion configuration fields must be JSON arrays")
        content = await file.read()
        if len(content) > _MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="Upload exceeds the 25 MiB ingestion limit")
        dataframe = load_file_from_bytes(content, file.filename or "")
        if len(dataframe.index) > _MAX_IMPORT_ROWS:
            raise HTTPException(status_code=413, detail="Import exceeds the 100,000 row limit")
        rows = dataframe.where(pd.notnull(dataframe), None).to_dict("records")
        statements = [
            *(create_index_query(item["type"], item["name"], item["label"], item["properties"]) for item in index_defs),
            *(create_constraint_query(item["type"], item["name"], item["label"], item["properties"]) for item in constraint_defs),
            *(create_node_import_query(item["label"], item["properties"], item.get("mergeKeys", [])) for item in node_defs if item.get("label") and item.get("properties")),
            *(create_relationship_import_query(item["type"], item["fromLabel"], item["toLabel"], item["fromProperty"], item["toProperty"]) for item in rel_defs if item.get("type") and item.get("fromLabel") and item.get("toLabel")),
        ]
        results = []
        for statement in filter(None, statements):
            try:
                query_with_timeout(statement, params={"rows": rows} if "UNWIND" in statement else None)
                results.append({"status": "success"})
            except Exception as exc:
                results.append({"status": "error", "error": str(exc)})
        return {"message": "Data ingestion completed", "results": results}
    except HTTPException:
        raise
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
