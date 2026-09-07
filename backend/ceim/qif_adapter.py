"""Strict QIF instance adapter for the CEIM contract.

The adapter recognizes only the QIF product, inspection-plan, and measurement
records declared in the QIF mapping pack. Unknown XML is not inferred into a
semantic type; it must receive a governed mapping-pack extension first.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any
from collections import Counter
import hashlib

from defusedxml import ElementTree as ET

from .contract import CEIMContract


def _local_name(tag: object) -> str:
    return str(tag or "").rsplit("}", 1)[-1].split(":")[-1]


def _attribute(element: Any, *names: str) -> str:
    values = {str(key).lower(): str(value).strip() for key, value in element.attrib.items()}
    for name in names:
        value = values.get(name.lower())
        if value:
            return value
    return ""


def _semantic_value(element: Any, *names: str) -> str:
    """Return an explicitly named QIF scalar without guessing its meaning.

    QIF characteristic values are commonly nested below their nominal record.
    We only read a named leaf, preserving the lexical representation and unit
    rather than coercing a possibly qualified value to a number.
    """
    wanted = {name.lower() for name in names}
    for child in element.iter():
        if _local_name(child.tag).lower() in wanted and not list(child):
            value = (child.text or "").strip()
            if value:
                return value
    return ""


@lru_cache(maxsize=1)
def _qif_schema(schema_path: str) -> Any:
    """Compile the bundled QIF document schema without fetching its W3C import."""
    from lxml import etree

    root = Path(schema_path).resolve()
    signature_schema = root.parent.parent / "QIFLibrary" / "xmldsig-core-schema.xsd"
    resolver = type(
        "QifSchemaResolver",
        (etree.Resolver,),
        {"resolve": lambda self, url, public_id, context: self.resolve_filename(str(signature_schema), context) if "xmldsig-core-schema.xsd" in url else None},
    )()
    parser = etree.XMLParser(no_network=True)
    parser.resolvers.add(resolver)
    return etree.XMLSchema(etree.parse(str(root), parser))


def validate_qif_instance(content: bytes, *, schema_root: Path | None = None) -> dict[str, Any]:
    """Validate a QIF instance against the bundled QIF 3.0 document XSD.

    This is deliberately separate from CEIM extraction: XSD conformance and a
    governed semantic mapping are complementary, not interchangeable checks.
    """
    if not content:
        raise ValueError("QIF content is empty")
    try:
        from lxml import etree
    except ImportError:
        return {"validated": False, "validator": "unavailable", "errors": ["lxml/libxml2 is unavailable in this runtime"]}
    document_schema = (schema_root or Path(__file__).resolve().parents[2] / "docs" / "xsd" / "QIFApplications") / "QIFDocument.xsd"
    if not document_schema.is_file():
        return {"validated": False, "validator": "unavailable", "errors": ["Bundled QIFDocument.xsd is unavailable"]}
    try:
        document = etree.fromstring(content, parser=etree.XMLParser(resolve_entities=False, no_network=True))
    except etree.XMLSyntaxError as exc:
        raise ValueError("QIF XML is invalid") from exc
    schema = _qif_schema(str(document_schema))
    conforms = schema.validate(document)
    return {
        "validated": True,
        "validator": "lxml/libxml2",
        "conforms": conforms,
        "errors": [str(error) for error in schema.error_log] if not conforms else [],
    }


def qif_to_ceim_batch(content: bytes, *, ceim: CEIMContract | None = None) -> dict[str, Any]:
    """Extract declared QIF records into a non-persisted CEIM batch."""
    if not content:
        raise ValueError("QIF content is empty")
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise ValueError("QIF XML is invalid") from exc
    if "qif" not in _local_name(root.tag).lower():
        raise ValueError("The supplied XML is not a QIF document")

    active_contract = ceim or CEIMContract()
    entities: list[dict[str, Any]] = []
    relationships: list[dict[str, Any]] = []
    known_ids: set[str] = set()
    measurements: list[tuple[str, str]] = []
    nominal_definitions: list[tuple[str, str, str]] = []
    part_links: list[tuple[str, str, str]] = []
    counts = {"parts": 0, "inspection_plans": 0, "measurement_results": 0, "features": 0, "characteristics": 0, "datums": 0, "datum_reference_frames": 0, "pmi_annotations": 0, "geometry_bodies": 0, "unresolved_references": 0}
    unmapped = Counter(_local_name(element.tag) for element in root.iter())
    mapped_source_counts: Counter[str] = Counter()
    primary_part_id = next(((child.text or "").strip() for element in root.iter() if _local_name(element.tag) == "RootPart" for child in element if _local_name(child.tag) == "Id" and (child.text or "").strip()), "")

    declared_types = {"Part", "InspectionPlan", "MeasurementResults"}
    type_families = {
        "FeatureDefinition": "FeatureDefinition", "FeatureNominal": "FeatureNominal",
        "CharacteristicDefinition": "CharacteristicDefinition", "CharacteristicNominal": "CharacteristicNominal",
        "DatumDefinition": "DatumDefinition", "DatumReferenceFrame": "DatumReferenceFrame",
        "Body": "Body", "PMIDisplay": "PMIDisplay", "AnnotationView": "AnnotationView",
    }
    for element in root.iter():
        original_type = _local_name(element.tag)
        source_type = original_type if original_type in declared_types else next((category for suffix, category in type_families.items() if original_type.endswith(suffix)), "")
        if not source_type:
            if original_type == "FolderPart" and primary_part_id:
                for child in element:
                    if _local_name(child.tag) == "BodyIds":
                        for identifier in child:
                            if _local_name(identifier.tag) == "Id" and (identifier.text or "").strip():
                                part_links.append(("PartBody", primary_part_id, identifier.text.strip()))
            continue
        source_id = _attribute(element, "id", "identifier", "uuid")
        if source_type == "PMIDisplay" and not source_id:
            source_id = f"pmi-{hashlib.sha256(ET.tostring(element, encoding='utf-8')).hexdigest()[:20]}"
        if not source_id:
            continue
        attributes = {
            "name": _attribute(element, "name", "label", "description") or original_type,
            "status": _attribute(element, "status", "state", "disposition"),
            "source_kind": original_type,
        }
        if source_type in {"CharacteristicDefinition", "CharacteristicNominal"}:
            attributes.update({
                "nominal_value": _semantic_value(element, "NominalValue", "ValueNominal", "DecimalValue"),
                "lower_limit": _semantic_value(element, "LowerLimit", "LowerTolerance"),
                "upper_limit": _semantic_value(element, "UpperLimit", "UpperTolerance"),
                "unit": _semantic_value(element, "Unit", "Units", "UnitLabel"),
            })
        entities.append(active_contract.normalize_entity(
            standard="qif",
            record={"source_type": source_type, "source_id": source_id, "attributes": attributes},
        ))
        known_ids.add(source_id)
        mapped_source_counts[original_type] += 1
        if source_type == "Part":
            counts["parts"] += 1
            relationship_lists = {
                "FeatureNominalIds": "PartFeatureNominal",
                "CharacteristicNominalIds": "PartCharacteristicNominal",
                "DatumDefinitionIds": "PartDatumDefinition",
                "DatumReferenceFrameIds": "PartDatumReferenceFrame",
            }
            for child in element:
                relationship_type = relationship_lists.get(_local_name(child.tag))
                if relationship_type:
                    for identifier in child:
                        if _local_name(identifier.tag) == "Id" and (identifier.text or "").strip():
                            part_links.append((relationship_type, source_id, identifier.text.strip()))
        elif source_type == "InspectionPlan":
            counts["inspection_plans"] += 1
        elif source_type == "MeasurementResults":
            counts["measurement_results"] += 1
            plan_id = _attribute(element, "inspectionplanid", "inspection_plan_id", "planid", "plan_id")
            if plan_id:
                measurements.append((source_id, plan_id))
        elif source_type.startswith("Feature"):
            counts["features"] += 1
        elif source_type.startswith("Characteristic"):
            counts["characteristics"] += 1
        elif source_type == "DatumDefinition":
            counts["datums"] += 1
        elif source_type == "DatumReferenceFrame":
            counts["datum_reference_frames"] += 1
        elif source_type in {"PMIDisplay", "AnnotationView"}:
            counts["pmi_annotations"] += 1
        elif source_type == "Body":
            counts["geometry_bodies"] += 1
        if source_type in {"FeatureNominal", "CharacteristicNominal"}:
            definition_name = "FeatureDefinitionId" if source_type == "FeatureNominal" else "CharacteristicDefinitionId"
            definition_id = next(((child.text or "").strip() for child in element.iter() if _local_name(child.tag) == definition_name and (child.text or "").strip()), "")
            if definition_id:
                nominal_definitions.append((source_type, source_id, definition_id))

    for measurement_id, plan_id in measurements:
        if plan_id not in known_ids:
            counts["unresolved_references"] += 1
            continue
        relationships.append(active_contract.normalize_relationship(
            standard="qif",
            record={"source_type": "MeasurementResults", "source_id": measurement_id, "target_id": plan_id},
        ))

    for relationship_type, part_id, target_id in [*part_links, *nominal_definitions]:
        if part_id not in known_ids or target_id not in known_ids:
            counts["unresolved_references"] += 1
            continue
        relationships.append(active_contract.normalize_relationship(
            standard="qif",
            record={"source_type": relationship_type, "source_id": part_id, "target_id": target_id},
        ))

    required_children = {
        "BodySet": "Body", "FeatureDefinitions": "FeatureDefinition",
        "FeatureNominals": "FeatureNominal", "CharacteristicDefinitions": "CharacteristicDefinition",
        "CharacteristicNominals": "CharacteristicNominal", "DatumDefinitions": "DatumDefinition",
        "DatumReferenceFrames": "DatumReferenceFrame", "PMIDisplaySet": "PMIDisplay",
    }
    unresolved_containers = [
        {"source_type": container, "count": unmapped[container]}
        for container, expected_suffix in sorted(required_children.items())
        if unmapped[container] and not any(name.endswith(expected_suffix) for name in mapped_source_counts)
    ]
    return {
        "standard": "qif",
        "entities": entities,
        "relationships": relationships,
        "source_summary": counts,
        "mapping_diagnostics": {
            "status": "review_required" if unresolved_containers else "complete_for_declared_profile",
            "unmapped_semantic_elements": unresolved_containers,
        },
    }
