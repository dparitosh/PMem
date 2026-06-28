from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any, Iterable

try:
    from pypdf import PdfReader
except Exception:  # pragma: no cover
    PdfReader = None

try:
    from docx import Document as DocxDocument
except Exception:  # pragma: no cover
    DocxDocument = None

try:
    from pptx import Presentation
except Exception:  # pragma: no cover
    Presentation = None

logger = logging.getLogger(__name__)

SUPPORTED_FORMATS = {
    "pdf": [".pdf"],
    "word": [".docx", ".doc"],
    "powerpoint": [".pptx", ".ppt"],
}

CHUNK_SIZE = 1400
CHUNK_OVERLAP = 180
UPSERT_DATASHEET_CHUNK = """
UNWIND $rows AS row
MERGE (d:DocumentAsset {source: row.source})
SET d.filename = row.filename,
    d.file_type = row.file_type,
    d.updated_at = datetime(),
    d.content_hash = row.content_hash,
    d.chunk_count = row.chunk_count,
    d.status = 'indexed'
MERGE (c:DatasheetChunk {source: row.source, chunk_id: row.chunk_id})
SET c.content = row.content,
    c.embedding = row.embedding,
    c.filename = row.filename,
    c.file_type = row.file_type,
    c.content_hash = row.content_hash,
    c.chunk_index = row.chunk_index,
    c.updated_at = datetime()
MERGE (d)-[:HAS_CHUNK]->(c)
"""


def get_format_description() -> dict[str, str]:
    return {
        "pdf": "Portable Document Format text extraction and DatasheetChunk indexing",
        "word": "Microsoft Word text extraction and DatasheetChunk indexing",
        "powerpoint": "Microsoft PowerPoint slide text extraction and DatasheetChunk indexing",
    }


def cleanup_temp_directory() -> None:
    return None


def runtime_status() -> dict[str, Any]:
    errors: list[str] = []
    embedder_available = False
    try:
        from backend.core.llm import EMBEDDER_AVAILABLE as _available
        embedder_available = bool(_available)
    except Exception as exc:
        errors.append(f"llm import: {exc}")

    try:
        from backend.Services.graph_embeddings import ensure_indexes_standalone as _ensure_indexes  # noqa: F401
    except Exception as exc:
        errors.append(f"graph_embeddings import: {exc}")

    return {
        "available": embedder_available and not errors,
        "embedder_available": embedder_available,
        "errors": errors,
    }


def _detect_format(file_path: Path) -> str:
    suffix = file_path.suffix.lower()
    for fmt, suffixes in SUPPORTED_FORMATS.items():
        if suffix in suffixes:
            return fmt
    raise ValueError(f"Unsupported document format: {suffix}")


def _extract_pdf_text(file_path: Path) -> str:
    if PdfReader is None:
        raise RuntimeError("pypdf is not available")
    reader = PdfReader(str(file_path))
    pages = []
    for index, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception as exc:
            logger.warning("PDF page extraction failed for %s page %s: %s", file_path.name, index, exc)
            text = ""
        text = text.strip()
        if text:
            pages.append(f"[Page {index}]\n{text}")
    return "\n\n".join(pages).strip()


def _extract_docx_text(file_path: Path) -> str:
    if DocxDocument is None:
        raise RuntimeError("python-docx is not available")
    document = DocxDocument(str(file_path))
    paragraphs = [p.text.strip() for p in document.paragraphs if p.text and p.text.strip()]
    return "\n".join(paragraphs).strip()


def _extract_pptx_text(file_path: Path) -> str:
    if Presentation is None:
        raise RuntimeError("python-pptx is not available")
    presentation = Presentation(str(file_path))
    slides = []
    for slide_index, slide in enumerate(presentation.slides, start=1):
        parts = []
        for shape in slide.shapes:
            text = getattr(shape, "text", "") or ""
            text = text.strip()
            if text:
                parts.append(text)
        if parts:
            slides.append(f"[Slide {slide_index}]\n" + "\n".join(parts))
    return "\n\n".join(slides).strip()


def extract_text_from_file(file_path: str | Path) -> dict[str, Any]:
    path = Path(file_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Document not found: {path}")
    file_type = _detect_format(path)
    if file_type == "pdf":
        text = _extract_pdf_text(path)
    elif file_type == "word":
        text = _extract_docx_text(path)
    elif file_type == "powerpoint":
        text = _extract_pptx_text(path)
    else:  # pragma: no cover
        raise ValueError(f"Unsupported document format: {path.suffix}")

    text = (text or "").strip()
    if not text:
        raise ValueError(f"No extractable text found in document: {path.name}")

    return {
        "path": str(path),
        "filename": path.name,
        "file_type": file_type,
        "text": text,
    }


def _chunk_document(text: str) -> list[str]:
    normalized = (text or "").strip()
    if not normalized:
        return []

    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(start + CHUNK_SIZE, len(normalized))
        if end < len(normalized):
            soft_break = normalized.rfind("\n", start, end)
            if soft_break <= start:
                soft_break = normalized.rfind(" ", start, end)
            if soft_break > start + 200:
                end = soft_break
        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(normalized):
            break
        start = max(end - CHUNK_OVERLAP, start + 1)
    return chunks


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _embed_texts(chunks: Iterable[str]) -> list[list[float]]:
    normalized_chunks = list(chunks)
    from backend.core.llm import EMBEDDER_AVAILABLE, embeddings
    if not EMBEDDER_AVAILABLE:
        raise RuntimeError("Embeddings model is unavailable")
    return embeddings.embed_documents(normalized_chunks)


def _upsert_datasheet_chunks(rows: list[dict[str, Any]]) -> None:
    from backend.Services.graph_embeddings import ensure_indexes_standalone
    from backend.core.db_config import get_config, get_driver
    ensure_indexes_standalone()
    config = get_config()
    driver = get_driver()
    with driver.session(database=config.database) as session:
        session.run(UPSERT_DATASHEET_CHUNK, rows=rows)


def process_documents_batch(file_paths: list[str], index_name: str = "datasheet_index") -> dict[str, Any]:
    status = runtime_status()
    if not status["embedder_available"]:
        raise RuntimeError("Document processing requires a working embedding backend")

    results: list[dict[str, Any]] = []
    success_count = 0
    failed_count = 0

    for raw_path in file_paths:
        try:
            extracted = extract_text_from_file(raw_path)
            chunks = _chunk_document(extracted["text"])
            chunk_embeddings = _embed_texts(chunks)
            content_hash = _hash_text(extracted["text"])
            rows = []
            for idx, (chunk_text, embedding) in enumerate(zip(chunks, chunk_embeddings), start=1):
                rows.append({
                    "source": extracted["path"],
                    "filename": extracted["filename"],
                    "file_type": extracted["file_type"],
                    "chunk_id": f"chunk_{idx:04d}",
                    "chunk_index": idx,
                    "chunk_count": len(chunks),
                    "content": chunk_text,
                    "embedding": embedding,
                    "content_hash": content_hash,
                })
            _upsert_datasheet_chunks(rows)
            results.append({
                "file": extracted["filename"],
                "path": extracted["path"],
                "file_type": extracted["file_type"],
                "status": "success",
                "chunks_created": len(rows),
                "index_name": index_name,
                "content_hash": content_hash,
            })
            success_count += 1
        except Exception as exc:
            logger.exception("Document processing failed for %s", raw_path)
            results.append({
                "file": Path(raw_path).name,
                "path": str(raw_path),
                "status": "failed",
                "error": str(exc),
                "index_name": index_name,
            })
            failed_count += 1

    return {
        "summary": {
            "total_files": len(file_paths),
            "successfully_processed": success_count,
            "failed_processing": failed_count,
        },
        "processing_results": results,
    }
