"""AP242 MBD extraction and safe Part-28 export boundary.

The extractor uses the legacy STEP parser as the source of truth.  It produces
traceable domain-model candidates for ontology/graph mapping.  A native AP242
Part-28 document is exported losslessly; converting arbitrary Part-21 CAD into
Part-28 is intentionally not claimed here because that requires a complete
ISO 10303 mapping and CAD-vendor conformance tests.
"""
from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from backend.Services.ap242_domain_model import describe_ap242_domain_model
from backend.Services.step_parser import parse_step_with_pmi
from backend.parsers.ap242_identity import is_ap242


class AP242MbdExchangeService:
    def extract(self, *, filename: str, content: bytes) -> dict[str, Any]:
        suffix = Path(filename).suffix.lower()
        if suffix not in {".stp", ".step", ".stpx", ".xml"}:
            raise ValueError("AP242 MBD extraction supports .stp, .step, .stpx, and AP242 XML files")
        with NamedTemporaryFile(suffix=suffix or ".stp", delete=False) as stream:
            stream.write(content)
            source = Path(stream.name)
        try:
            document = parse_step_with_pmi(source)
        finally:
            source.unlink(missing_ok=True)

        if not self._is_ap242(document.metadata.file_schema, document.metadata.namespace, content):
            raise ValueError("The source does not identify an AP242 STEP or AP242 Domain Model representation")
        candidates = [
            *[self._cad_candidate(item, "Part") for item in document.cad_products],
            *[self._cad_candidate(item, "ShapeRepresentation") for item in document.cad_representations],
            *[self._cad_candidate(item, "TopologyEntity") for item in document.cad_topology],
            *[self._cad_candidate(item, "GeometricModel") for item in document.cad_geometry],
            *[self._tolerance_candidate(item) for item in document.geometric_tolerances],
            *[self._datum_candidate(item) for item in document.datums],
            *[self._dimension_candidate(item) for item in document.dimensions],
            *[self._annotation_candidate(item) for item in document.annotations],
            *[self._presentation_candidate(item) for item in document.graphic_presentations],
            *[self._view_candidate(item) for item in document.saved_views],
        ]
        references = [
            {"source_step_id": entity.step_id, "target_step_id": reference, "relationship": "references"}
            for entity in document.entities for reference in entity.ref_ids
        ]
        return {
            "standard": "ap242",
            "source_representation": "part28-xml" if document.metadata.format == "stpx" else "part21-step",
            "domain_model": describe_ap242_domain_model(),
            "file": {
                "filename": filename,
                "file_schema": document.metadata.file_schema,
                "namespace": document.metadata.namespace,
                "schema_location": document.metadata.schema_location,
            },
            "coverage": {
                "raw_step_entities": len(document.entities),
                "products": len(document.cad_products),
                "representations": len(document.cad_representations),
                "topology": len(document.cad_topology),
                "geometry": len(document.cad_geometry),
                "geometric_tolerances": len(document.geometric_tolerances),
                "datums": len(document.datums),
                "dimensions": len(document.dimensions),
                "annotations": len(document.annotations),
                "graphic_presentations": len(document.graphic_presentations),
                "saved_views": len(document.saved_views),
            },
            "domain_candidates": candidates,
            "references": references,
            "export": {
                "part28_xml": document.metadata.format == "stpx",
                "part21_step": document.metadata.format == "p21",
                "message": (
                    "The AP242 Part-28 XML source can be exported unchanged."
                    if document.metadata.format == "stpx"
                    else "The source is AP242 Part-21. Export it as native STEP; a Part-21-to-Part-28 conversion requires a complete conformance mapping."
                ),
            },
            "conformance": {
                "status": "not_validated",
                "xsd_validation": "not_implemented",
                "schematron_validation": "not_implemented",
                "cad_application_validation": "not_implemented",
                "message": "Extraction is traceable, but CAD interchange conformance requires the applicable AP242 XSD/Schematron profile and target-CAD validation.",
            },
        }

    def export_part28(self, *, filename: str, content: bytes) -> bytes:
        result = self.extract(filename=filename, content=content)
        if not result["export"]["part28_xml"]:
            raise ValueError("Only an existing AP242 Part-28 (.stpx/XML) source can be re-exported as XML; converting Part-21 to Part-28 needs a complete conformance mapping")
        return content

    @staticmethod
    def _is_ap242(file_schema: str | None, namespace: str, content: bytes) -> bool:
        return is_ap242(file_schema, namespace, content)

    @staticmethod
    def _cad_candidate(item: Any, domain_type: str) -> dict[str, Any]:
        return {"step_id": item.id, "source_entity": item.entity_type, "domain_candidate": domain_type, "id": item.external_id, "name": item.name, "description": item.description, "references": item.ref_ids}

    @staticmethod
    def _tolerance_candidate(item: Any) -> dict[str, Any]:
        return {"step_id": item.id, "source_entity": item.tolerance_type, "domain_candidate": "GeometricTolerance", "name": item.name, "description": item.description, "magnitude": item.magnitude, "datum_system_refs": item.datum_system_refs, "toleranced_feature_refs": item.toleranced_feature_refs}

    @staticmethod
    def _datum_candidate(item: Any) -> dict[str, Any]:
        return {"step_id": item.id, "source_entity": item.datum_type, "domain_candidate": "GeneralDatumReference", "label": item.label, "name": item.name, "feature_refs": item.feature_refs}

    @staticmethod
    def _dimension_candidate(item: Any) -> dict[str, Any]:
        return {"step_id": item.id, "source_entity": item.dimension_type, "domain_candidate": "GeometricDimension", "name": item.name, "description": item.description, "nominal_value": item.nominal_value, "lower_tolerance": item.lower_tolerance, "upper_tolerance": item.upper_tolerance, "feature_refs": item.feature_refs}

    @staticmethod
    def _annotation_candidate(item: Any) -> dict[str, Any]:
        return {"step_id": item.id, "source_entity": item.annotation_type, "domain_candidate": "Annotation", "name": item.name, "text": item.text, "feature_refs": item.feature_refs, "view_refs": item.view_refs}

    @staticmethod
    def _presentation_candidate(item: Any) -> dict[str, Any]:
        return {"step_id": item.id, "source_entity": item.presentation_type, "domain_candidate": "GraphicPresentation", "annotation_refs": item.annotation_refs, "geometry_refs": item.geometry_refs, "view_refs": item.view_refs, "style_refs": item.style_refs}

    @staticmethod
    def _view_candidate(item: Any) -> dict[str, Any]:
        return {"step_id": item.id, "source_entity": item.view_type, "domain_candidate": "ViewContext", "name": item.name, "annotation_refs": item.annotation_refs, "geometry_refs": item.geometry_refs, "presentation_refs": item.presentation_refs}


ap242_mbd = AP242MbdExchangeService()
