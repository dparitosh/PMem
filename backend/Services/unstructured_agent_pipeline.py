"""Agentic planning helpers for unstructured ingestion.

This module does not run OCR/LLM tools directly. It produces an auditable plan so
import orchestration can choose the right extraction tools per document type.
"""

from __future__ import annotations

from typing import Any, Dict, List


def classify_document(metadata: Dict[str, Any]) -> Dict[str, Any]:
    metadata = metadata if isinstance(metadata, dict) else {}
    filename = str(metadata.get("filename") or metadata.get("source_filename") or "").lower()
    content_type = str(metadata.get("content_type") or metadata.get("mime_type") or "").lower()
    extension = filename.rsplit(".", 1)[-1] if "." in filename else ""
    is_visual = extension in {"pdf", "png", "jpg", "jpeg", "tiff"} or "image" in content_type or "pdf" in content_type
    is_tabular = extension in {"csv", "xlsx", "xls"}
    is_office = extension in {"docx", "pptx", "html", "htm"}
    is_legacy_office = extension in {"doc", "ppt"}
    upload_extensions = {"pdf", "docx", "pptx", "txt", "md", "html", "htm"}
    return {
        "extension": extension,
        "is_visual": is_visual,
        "is_tabular": is_tabular,
        "is_office": is_office,
        "is_legacy_office": is_legacy_office,
        "supported_for_upload": extension in upload_extensions,
        "likely_unstructured": is_visual or is_office or is_legacy_office or extension in {"txt", "md"},
    }


def build_unstructured_plan(metadata: Dict[str, Any]) -> Dict[str, Any]:
    classification = classify_document(metadata)
    steps: List[Dict[str, str]] = []
    warnings: List[str] = []
    if classification["is_legacy_office"]:
        warnings.append("Legacy .doc and .ppt files must be converted to .docx or .pptx before upload.")
    if classification["is_visual"]:
        steps.extend([
            {"tool": "layout_analyzer", "purpose": "Detect sections, figures, captions, and tables."},
            {"tool": "text_extractor", "purpose": "Extract the native text layer when one is available."},
            {"tool": "optional_ocr", "purpose": "Use a separately configured OCR enhancement only when native extraction finds no text."},
        ])
    if classification["is_tabular"]:
        steps.append({"tool": "table_extractor", "purpose": "Extract rows, columns, datatypes, and candidate keys."})
    if classification["is_office"] or classification["extension"] in {"txt", "md"}:
        steps.append({"tool": "structured_text_extractor", "purpose": "Extract headings, paragraphs, lists, and requirement-like statements."})
    steps.extend([
        {"tool": "chunker", "purpose": "Create traceable chunks with source offsets."},
        {"tool": "embedding_generator", "purpose": "Generate one validated vector per traceable chunk."},
        {"tool": "datasheet_index_writer", "purpose": "Write DocumentAsset and DatasheetChunk records to the configured Neo4j retrieval index."},
        {"tool": "semantic_candidate_extractor", "purpose": "Create deterministic requirement and engineering-parameter candidates for review."},
        {"tool": "ontology_mapping_proposal_writer", "purpose": "Write review-only type mapping proposals without committing semantic entity nodes."},
    ])
    return {
        "classification": classification,
        "steps": steps,
        "warnings": warnings,
        "requires_human_approval": False,
        "semantic_proposals_require_human_approval": True,
        "writes_to_neo4j": True,
        "retains_source_artifact": True,
        "execution_modes": {
            "durable_job": {"retains_source_artifact": True, "supports_status": True, "supports_cancellation": True},
            "legacy_synchronous": {"retains_source_artifact": False, "supports_status": False, "supports_cancellation": False},
        },
        "not_performed": [
            "automatic semantic proposal approval",
            "automatic creation of requirement or parameter entity nodes",
        ],
    }
