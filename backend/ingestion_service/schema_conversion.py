"""Uniform schema/instance conversion boundary for engineering formats."""
from __future__ import annotations

import threading
import json
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
from backend.artifact_store import ArtifactStore
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
        # A generated Turtle string is useful for an interactive preview, but
        # it was previously ephemeral. Retain the source, serialization and a
        # compact analytics profile so a steward can create a real, immutable
        # data product from the same evidence after approving a semantic
        # release. Conversion itself deliberately has no product/publication
        # authority.
        store = ArtifactStore()
        source_artifact = store.ingest_bytes(
            content, filename=filename, kind="engineering-schema-source",
            media_type="application/xml" if file_type == FileType.XSD else "text/plain",
            provenance={"format": file_type.value, "source_kind": source_kind},
        )
        turtle_bytes = turtle.encode("utf-8") if isinstance(turtle, str) else bytes(turtle)
        turtle_artifact = store.ingest_bytes(
            turtle_bytes, filename=f"{stem}.ttl", kind="serialized-ontology",
            media_type="text/turtle", provenance={"source_artifact_id": source_artifact["artifact_id"], "format": file_type.value},
        )
        analytics = {
            "contract": "schema-analytics-profile-v1",
            "source_artifact_id": source_artifact["artifact_id"],
            "serialization_artifact_id": turtle_artifact["artifact_id"],
            "format": str(generated.get("format") or file_type.value.upper()),
            "source_kind": source_kind,
            "ontology": {"name": str(generated.get("schema_name") or generated.get("ontology_name") or stem), "prefix": ontology_prefix, "base_uri": base_uri},
            "statistics": generated,
            "schema_validation": schema_validation,
        }
        analytics_artifact = store.ingest_bytes(
            json.dumps(analytics, sort_keys=True, default=str).encode("utf-8"),
            filename=f"{stem}-schema-analytics.json", kind="schema-analytics-profile",
            media_type="application/json", provenance={"source_artifact_id": source_artifact["artifact_id"], "serialization_artifact_id": turtle_artifact["artifact_id"]},
        )
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
            "artifacts": {
                "source": source_artifact["artifact_id"], "serialization": turtle_artifact["artifact_id"],
                "analytics_profile": analytics_artifact["artifact_id"],
            },
            "data_product_draft": {
                "contract": "schema-analytics-data-product-v1",
                "name": f"{stem} schema analytics",
                "domain": "semantic-engineering",
                "artifacts": [source_artifact["artifact_id"], turtle_artifact["artifact_id"], analytics_artifact["artifact_id"]],
                "quality_status": "validated" if not (schema_validation or {}).get("errors") else "requires_review",
                "publication_requirements": ["approved semantic release", "data-product steward approval", "explicit Data Product API publish request"],
            },
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
