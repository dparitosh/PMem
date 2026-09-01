"""Uniform schema/instance conversion boundary for engineering formats."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.Services.import_file_types import FileFormatDetector, FileType
from backend.Services.owl_generation_service import OWLGenerationService


_SOURCE_KINDS = {
    FileType.EXPRESS: "schema",
    FileType.STEP: "instance",
    FileType.XMI: "schema",
    FileType.XSD: "schema",
}


class EngineeringSchemaConverter:
    """Convert supported engineering files into a common, non-publishing contract."""

    def convert(self, *, filename: str, content: bytes) -> dict[str, Any]:
        file_type = FileFormatDetector.detect(filename)
        if file_type not in _SOURCE_KINDS:
            raise ValueError("Supported conversion formats are .exp, .stp, .step, .stpx, .xmi, and .xsd")
        turtle, generated = OWLGenerationService.generate_owl(content, filename)
        stem = Path(filename).stem or "ontology"
        source_kind = _SOURCE_KINDS[file_type]
        ontology_prefix = str(generated.get("ontology_prefix") or ("step" if file_type == FileType.STEP else file_type.value))
        base_uri = str(generated.get("base_uri") or f"http://depo-onto.local/{file_type.value}#{stem}/")
        return {
            "format": str(generated.get("format") or file_type.value.upper()),
            "source_kind": source_kind,
            "filename": filename,
            "ontology": {
                "name": str(generated.get("schema_name") or generated.get("ontology_name") or stem),
                "prefix": ontology_prefix,
                "base_uri": base_uri,
                "turtle": turtle,
            },
            "statistics": generated,
            "next_action": "Register the generated Turtle with the ontology service, then use the governed publish workflow.",
        }


converter = EngineeringSchemaConverter()
