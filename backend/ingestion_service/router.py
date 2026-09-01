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
import json
import pandas as pd

router = APIRouter(tags=["ingestion"])


@router.get("/ingestion/health")
def health() -> dict:
    return {"status": "ok", "service": "ingestion", "contract": "v1"}


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
