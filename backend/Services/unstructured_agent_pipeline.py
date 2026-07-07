"""Agentic planning helpers for unstructured ingestion.

This module does not run OCR/LLM tools directly. It produces an auditable plan so
import orchestration can choose the right extraction tools per document type.
"""

from __future__ import annotations

from typing import Any, Dict, List


def classify_document(metadata: Dict[str, Any]) -> Dict[str, Any]:
    filename = str(metadata.get("filename") or metadata.get("source_filename") or "").lower()
    content_type = str(metadata.get("content_type") or metadata.get("mime_type") or "").lower()
    extension = filename.rsplit(".", 1)[-1] if "." in filename else ""
    is_visual = extension in {"pdf", "png", "jpg", "jpeg", "tiff"} or "image" in content_type or "pdf" in content_type
    is_tabular = extension in {"csv", "xlsx", "xls"}
    is_office = extension in {"doc", "docx", "ppt", "pptx", "html", "htm"}
    return {
        "extension": extension,
        "is_visual": is_visual,
        "is_tabular": is_tabular,
        "is_office": is_office,
        "likely_unstructured": is_visual or is_office or extension in {"txt", "md"},
    }


def build_unstructured_plan(metadata: Dict[str, Any]) -> Dict[str, Any]:
    classification = classify_document(metadata)
    steps: List[Dict[str, str]] = []
    if classification["is_visual"]:
        steps.extend([
            {"tool": "layout_analyzer", "purpose": "Detect sections, figures, captions, and tables."},
            {"tool": "ocr", "purpose": "Extract text from scanned or visual regions."},
            {"tool": "image_captioner", "purpose": "Summarize engineering diagrams and figures."},
        ])
    if classification["is_tabular"]:
        steps.append({"tool": "table_extractor", "purpose": "Extract rows, columns, datatypes, and candidate keys."})
    if classification["is_office"] or classification["extension"] in {"txt", "md"}:
        steps.append({"tool": "structured_text_extractor", "purpose": "Extract headings, paragraphs, lists, and requirement-like statements."})
    steps.extend([
        {"tool": "chunker", "purpose": "Create traceable chunks with source offsets."},
        {"tool": "entity_relationship_extractor", "purpose": "Extract candidate requirements, parts, functions, parameters, and relationships."},
        {"tool": "semantic_mapper", "purpose": "Map extracted terms to ontology classes/properties."},
        {"tool": "validation", "purpose": "Flag low-confidence mappings, duplicates, orphan concepts, and missing properties."},
        {"tool": "proposal_writer", "purpose": "Create human-approved graph update proposals; do not mutate Neo4j directly."},
    ])
    return {"classification": classification, "steps": steps, "requires_human_approval": True}
