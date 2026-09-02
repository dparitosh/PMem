"""Uniform schema/instance conversion boundary for engineering formats."""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any
from defusedxml import ElementTree as ET

from backend.Services.import_file_types import FileFormatDetector, FileType
from backend.Services.ap242_domain_model import (
    AP242_DOMAIN_MODEL_NAMESPACE,
    AP242_MBD_BOM_NAMESPACE,
    is_ap242_domain_model_namespace,
)
from backend.Services.owl_generation_service import OWLGenerationService
from .xsd_validation import inspect_xsd_structure


_SOURCE_KINDS = {
    FileType.EXPRESS: "schema",
    FileType.STEP: "instance",
    FileType.XMI: "schema",
    FileType.XSD: "schema",
}

# XSD-to-OWL conversion can be CPU intensive for standards such as AP242.
# The standalone service normally runs one process; this guard rejects a
# concurrent heavy conversion instead of allowing duplicate uploads to exhaust
# that process.  Multi-process deployments should route this endpoint through
# their gateway with the same one-at-a-time policy.
_XSD_CONVERSION_LOCK = threading.Lock()


class EngineeringSchemaConverter:
    """Convert supported engineering files into a common, non-publishing contract."""

    @staticmethod
    def _ap242_representation(*, filename: str, content: bytes, file_type: FileType) -> str | None:
        """Identify AP242 representation without conflating schema and instance inputs."""
        name = Path(filename).name.lower()
        text = content[:64 * 1024].decode("utf-8", errors="ignore").lower()
        if file_type == FileType.XSD:
            try:
                namespace = (ET.fromstring(content).get("targetNamespace") or "").rstrip("/#")
            except ET.ParseError:
                namespace = ""
            if namespace == AP242_DOMAIN_MODEL_NAMESPACE.rstrip("/#") or "domainmodel" in name:
                return "ap242-domain-model-xsd"
            if namespace == AP242_MBD_BOM_NAMESPACE.rstrip("/#") or name == "bom.xsd":
                return "ap242-business-object-model-xsd"
        if file_type == FileType.STEP:
            if "ap242" in text or "managed_model_based_3d_engineering" in text:
                return "ap242-step-instance"
            if content.lstrip().startswith(b"<"):
                try:
                    root = ET.fromstring(content)
                    namespace = root.tag.partition("}")[0].removeprefix("{")
                    schema_location = " ".join(root.attrib.values()).lower()
                    if is_ap242_domain_model_namespace(namespace) or "10303/-4442" in schema_location:
                        return "ap242-step-instance"
                except ET.ParseError:
                    pass
        if file_type == FileType.EXPRESS and ("ap242" in name or "managed_model_based_3d_engineering" in text):
            return "ap242-express-schema"
        return None

    def convert(self, *, filename: str, content: bytes) -> dict[str, Any]:
        file_type = FileFormatDetector.detect(filename)
        if file_type not in _SOURCE_KINDS:
            raise ValueError("Supported conversion formats are .exp, .stp, .step, .stpx, .xmi, and .xsd")
        schema_validation = inspect_xsd_structure(content) if file_type == FileType.XSD else None
        if file_type == FileType.XSD:
            if not _XSD_CONVERSION_LOCK.acquire(blocking=False):
                raise ValueError("Another XSD-to-ontology conversion is running; retry after it completes")
            try:
                turtle, generated = OWLGenerationService.generate_owl(content, filename)
            finally:
                _XSD_CONVERSION_LOCK.release()
        else:
            turtle, generated = OWLGenerationService.generate_owl(content, filename)
        stem = Path(filename).stem or "ontology"
        source_kind = _SOURCE_KINDS[file_type]
        ap242_representation = self._ap242_representation(filename=filename, content=content, file_type=file_type)
        ontology_prefix = str(generated.get("ontology_prefix") or ("step" if file_type == FileType.STEP else file_type.value))
        base_uri = str(generated.get("base_uri") or f"http://depo-onto.local/{file_type.value}#{stem}/")
        result = {
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
        if ap242_representation:
            result["standard"] = "ap242"
            result["adapter"] = ap242_representation
            result["next_action"] = (
                "Register AP242 XSD ontology classes/properties before publishing STEP instances."
                if source_kind == "schema"
                else "Publish STEP instances only after the AP242 ontology schema is registered."
            )
        if schema_validation is not None:
            result["schema_validation"] = schema_validation
        return result


converter = EngineeringSchemaConverter()
