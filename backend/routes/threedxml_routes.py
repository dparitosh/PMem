"""
3DXML API routes aligned with the shared ontology upload and registry flow.
"""

import os

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from typing import List, Optional
import logging

from ..Services.threedxml_import_service import (
    DEFAULT_3DXML_PREFIX,
    ThreeDXMLImportService,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ontology", tags=["3DXML Extraction"])
MAX_3DXML_FILE_SIZE = int(os.getenv("MAX_3DXML_FILE_SIZE", str(500 * 1024 * 1024)))


async def _read_upload_with_limit(file: UploadFile, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(1024 * 1024):
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(status_code=413, detail="3DXML file exceeds the configured size limit")
        chunks.append(chunk)
    return b"".join(chunks)


class ExtractionResponse(BaseModel):
    status: str
    task_id: str
    ontology_id: str
    ontology_name: str
    prefix: str
    entities_extracted: int
    relationships_extracted: int
    entity_types: List[str]
    message: str


class ExtractionStatus(BaseModel):
    task_id: str
    status: str
    progress: float
    ontology_id: str
    prefix: Optional[str] = None
    entities_extracted: Optional[int] = None
    relationships_extracted: Optional[int] = None
    entity_types: List[str] = []
    error: Optional[str] = None


@router.post("/extract-3dxml", response_model=ExtractionResponse)
async def extract_3dxml_ontology(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    ontology_name: str = Form("3DEXPERIENCE_EXTRACTED"),
    prefix: str = Form(DEFAULT_3DXML_PREFIX),
    load_to_neo4j: bool = Form(True),
):
    """Upload a 3DXML file, register it in the ontology catalog, and optionally push it to Neo4j."""
    try:
        file_content = await _read_upload_with_limit(file, MAX_3DXML_FILE_SIZE)
        result = ThreeDXMLImportService.register_upload(
            filename=file.filename or "",
            file_content=file_content,
            ontology_name=ontology_name,
            prefix=prefix,
            load_to_neo4j=load_to_neo4j,
        )

        if load_to_neo4j:
            background_tasks.add_task(
                ThreeDXMLImportService.push_to_neo4j,
                result["ontology_id"],
            )

        message = (
            f"3DXML ontology '{ontology_name}' registered"
            f"{' and queued for Neo4j load' if load_to_neo4j else ''}."
        )
        return ExtractionResponse(
            status="success",
            task_id=result["ontology_id"],
            ontology_id=result["ontology_id"],
            ontology_name=ontology_name,
            prefix=result["prefix"],
            entities_extracted=result["entities_extracted"],
            relationships_extracted=result["relationships_extracted"],
            entity_types=result["entity_types"],
            message=message,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("3DXML extraction failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="3DXML extraction failed") from exc


@router.get("/3dxml/status/{task_id}", response_model=ExtractionStatus)
async def get_extraction_status(task_id: str):
    """Read 3DXML extraction status from the shared ontology registry metadata."""
    try:
        return ExtractionStatus(**ThreeDXMLImportService.get_status(task_id))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/3dxml/formats")
async def get_supported_formats():
    """Return supported 3DXML-oriented ontology source formats."""
    return ThreeDXMLImportService.supported_formats()
