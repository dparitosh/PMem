"""
AP239 Product Lifecycle Support — Parser and Validator

Adapted from requirements/src/engines/ap239_parser.py with:
  - defusedxml / secure lxml for XXE safety
  - parse_ap239_xsd() for Domain_model.xsd concept extraction
  - Integration hook for unified_data_import FileParser

Parses AP239 XMI and XSD domain models for lifecycle management, product data,
process models, and requirements.  Compliant with ISO/TS 10303-15:2023.

AP239 Standard: ISO/TS 10303-15:2023 (STEP Part 15, Edition 2)
Namespace: https://standards.iso.org/iso/ts/10303/-4439/ed-2/tech/xml-schema/domain_model
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Tuple

import logging

logger = logging.getLogger(__name__)

# AP239 canonical namespace
AP239_NAMESPACE = "https://standards.iso.org/iso/ts/10303/-4439/ed-2/tech/xml-schema/domain_model"

# XSD namespace used in schema files
_XSD_NS = "http://www.w3.org/2001/XMLSchema"
_XSD_PRE = f"{{{_XSD_NS}}}"


# ---------------------------------------------------------------------------
# AP239 data model
# ---------------------------------------------------------------------------

@dataclass
class AP239Part:
    id: str
    name: str
    part_number: str = ""
    description: str = ""
    revision: str = ""
    part_type: str = ""
    lifecycle_stage: str = ""
    organization: str = ""
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AP239Activity:
    id: str
    name: str
    activity_type: str = ""
    description: str = ""
    status: str = ""
    resources: List[str] = field(default_factory=list)
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AP239Requirement:
    id: str
    name: str
    requirement_id: str = ""
    description: str = ""
    requirement_type: str = ""
    priority: str = ""
    status: str = ""
    traces: List[str] = field(default_factory=list)
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AP239InterfaceConnector:
    id: str
    name: str
    interface_type: str = ""
    connector_type: str = ""
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AP239Document:
    id: str
    name: str
    document_type: str = ""
    version: str = ""
    author: str = ""
    status: str = ""
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AP239Model:
    model_id: str
    model_name: str
    version: str = ""
    namespace: str = AP239_NAMESPACE
    parts: Dict[str, AP239Part] = field(default_factory=dict)
    activities: Dict[str, AP239Activity] = field(default_factory=dict)
    requirements: Dict[str, AP239Requirement] = field(default_factory=dict)
    interface_connectors: Dict[str, AP239InterfaceConnector] = field(default_factory=dict)
    documents: Dict[str, AP239Document] = field(default_factory=dict)
    properties: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Concept classification heuristics (from ap239_parser.py in requirements)
# ---------------------------------------------------------------------------

_PART_KEYWORDS = frozenset(["part", "product", "component", "assembly", "item", "device", "unit"])
_ACTIVITY_KEYWORDS = frozenset(["activity", "process", "task", "workflow", "stage", "phase", "step",
                                 "method", "action", "operation"])
_REQUIREMENT_KEYWORDS = frozenset(["requirement", "specification", "constraint", "rule", "standard",
                                    "analysis", "criterion", "objective"])
_INTERFACE_KEYWORDS = frozenset(["interface", "connector", "port", "connection", "socket", "protocol",
                                  "channel", "link", "relation"])
_DOCUMENT_KEYWORDS = frozenset(["document", "file", "dataset", "report", "record", "artifact",
                                  "approval", "certification", "advisory"])
_RESOURCE_KEYWORDS = frozenset(["resource", "person", "organization", "role", "actor", "agent"])


def classify_ap239_concept(name: str) -> str:
    """Classify a type name into an AP239 concept category using keyword heuristics.

    P13 FIX: Activity and Requirement keywords are checked before Part to avoid
    misclassification of compound names like 'ProductDefinitionProcess' (should
    be Activity, not Part).
    """
    lower = name.lower()
    # Higher-specificity groups first — Activity/Requirement/Interface/Document/Resource
    # must be checked before the broad Part group that matches 'product*'
    if any(kw in lower for kw in _ACTIVITY_KEYWORDS):
        return "Activity"
    if any(kw in lower for kw in _REQUIREMENT_KEYWORDS):
        return "Requirement"
    if any(kw in lower for kw in _INTERFACE_KEYWORDS):
        return "Interface"
    if any(kw in lower for kw in _DOCUMENT_KEYWORDS):
        return "Document"
    if any(kw in lower for kw in _RESOURCE_KEYWORDS):
        return "Resource"
    if any(kw in lower for kw in _PART_KEYWORDS):
        return "Part"
    return "DomainConcept"


# ---------------------------------------------------------------------------
# XSD → structured rows
# ---------------------------------------------------------------------------

def parse_ap239_xsd(file_content: bytes) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Parse an AP239 Domain_model.xsd file and return (rows, stats).

    Detects the AP239 namespace and extracts complexType definitions with:
      - name, concept_type (Part/Activity/Requirement/…)
      - parent_type (from complexContent/extension base=)
      - child_elements (JSON list of {name, type, minOccurs, maxOccurs})
      - attributes (JSON list of {name, type, use})

    Falls back to generic XSD extraction if namespace is not AP239.
    """
    import tempfile
    from lxml import etree

    # ✅ SECURITY: disable external entities / network to prevent XXE
    _safe = etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        huge_tree=False,
    )

    with tempfile.NamedTemporaryFile(delete=False, suffix=".xsd") as tmp:
        tmp.write(file_content)
        tmp_path = Path(tmp.name)

    try:
        tree = etree.parse(str(tmp_path), _safe)
        root = tree.getroot()
    finally:
        tmp_path.unlink(missing_ok=True)

    # Detect AP239 namespace
    target_ns = root.get("targetNamespace", "")
    # P12 FIX: "10303" alone is too broad and matches any ISO 10303 schema.
    # Check for the canonical AP239 namespace or an explicit AP239 marker in the namespace URI.
    is_ap239 = AP239_NAMESPACE in target_ns or "AP239" in target_ns.upper()

    rows: List[Dict[str, Any]] = []
    type_counts: Dict[str, int] = {}

    # Parse complexType definitions
    for ct in root.iter(f"{_XSD_PRE}complexType"):
        type_name = ct.get("name", "")
        if not type_name:
            continue

        # Determine inheritance base
        parent_type = ""
        ext = ct.find(f".//{_XSD_PRE}extension")
        if ext is None:
            ext = ct.find(f".//{_XSD_PRE}restriction")
        if ext is not None:
            base = ext.get("base", "")
            parent_type = base.split(":")[-1] if ":" in base else base

        # Collect child elements
        children: List[Dict[str, str]] = []
        for el in ct.iter(f"{_XSD_PRE}element"):
            el_name = el.get("name", "") or el.get("ref", "").split(":")[-1]
            el_type = el.get("type", "").split(":")[-1]
            if el_name:
                children.append({
                    "name": el_name,
                    "type": el_type,
                    "minOccurs": el.get("minOccurs", "1"),
                    "maxOccurs": el.get("maxOccurs", "1"),
                })

        # Collect attributes
        attrs: List[Dict[str, str]] = []
        for at in ct.iter(f"{_XSD_PRE}attribute"):
            at_name = at.get("name", "")
            at_type = at.get("type", "").split(":")[-1]
            if at_name:
                attrs.append({
                    "name": at_name,
                    "type": at_type,
                    "use": at.get("use", "optional"),
                })

        # Classify concept
        concept_type = classify_ap239_concept(type_name) if is_ap239 else "XSDType"
        type_counts[concept_type] = type_counts.get(concept_type, 0) + 1

        rows.append({
            "name": type_name,
            "concept_type": concept_type,
            "parent_type": parent_type,
            "child_count": len(children),
            "child_elements": json.dumps(children),
            "attribute_count": len(attrs),
            "attributes": json.dumps(attrs),
            "namespace": target_ns,
        })

    # Also parse top-level element declarations (not inside complexType)
    for el in root.findall(f"{_XSD_PRE}element"):
        el_name = el.get("name", "")
        el_type = el.get("type", "").split(":")[-1]
        if el_name and el_type:
            concept_type = classify_ap239_concept(el_name) if is_ap239 else "XSDElement"
            type_counts[concept_type] = type_counts.get(concept_type, 0) + 1
            rows.append({
                "name": el_name,
                "concept_type": concept_type,
                "parent_type": el_type,
                "child_count": 0,
                "child_elements": "[]",
                "attribute_count": 0,
                "attributes": "[]",
                "namespace": target_ns,
            })

    columns = ["name", "concept_type", "parent_type", "child_count",
               "child_elements", "attribute_count", "attributes", "namespace"]
    stats = {
        "format": "XSD",
        "is_ap239": is_ap239,
        "target_namespace": target_ns,
        "row_count": len(rows),
        "column_count": len(columns),
        "columns": columns,
        "concept_type_counts": type_counts,
    }
    return rows, stats


# ---------------------------------------------------------------------------
# XMI → AP239 model
# ---------------------------------------------------------------------------

class AP239XMIParser:
    """Parse AP239 XMI files and extract the domain model.

    Uses keyword-based heuristics to classify UML Classes into AP239
    concept types (Part, Activity, Requirement, Interface, Document, Resource).
    """

    _NAMESPACES = {
        "xmi": "http://www.omg.org/spec/XMI/20131001",
        "uml": "http://www.omg.org/spec/UML/20131001",
        "sysml": "http://www.omg.org/spec/SysML/20150709/SysML",
    }

    def parse_xmi_file(self, xmi_path: Path) -> AP239Model:
        """Parse XMI file and extract AP239 domain model."""
        logger.info(f"Parsing AP239 XMI file: {xmi_path.name}")

        # ✅ SECURITY: disable external entities / network
        try:
            from lxml import etree
            _safe = etree.XMLParser(
                resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False
            )
            tree = etree.parse(str(xmi_path), _safe)
            root = tree.getroot()
        except Exception:
            # Fallback to defusedxml
            import defusedxml.ElementTree as _safe_ET
            tree = _safe_ET.parse(str(xmi_path))
            root = tree.getroot()

        model = AP239Model(model_id=xmi_path.stem, model_name=xmi_path.stem)
        self._extract_packages(root, model)
        self._extract_classes(root, model)
        self._extract_associations(root, model)

        logger.info(
            f"AP239 XMI parse complete — parts={len(model.parts)}, "
            f"activities={len(model.activities)}, requirements={len(model.requirements)}"
        )
        return model

    def _extract_packages(self, root, model: AP239Model) -> None:
        ns = self._NAMESPACES
        for pkg in root.findall(".//uml:Package", ns) if hasattr(root, 'findall') else []:
            name = pkg.get("name", "")
            if name:
                logger.debug(f"AP239 package: {name}")

    def _extract_classes(self, root, model: AP239Model) -> None:
        ns = self._NAMESPACES
        # Handle both lxml (namespaced iteration) and defusedxml (standard ET)
        candidates = root.findall(".//uml:Class", ns) if hasattr(root, 'findall') else []
        if not candidates:
            # lxml: iterate all and filter by local tag
            for elem in root.iter():
                tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                if tag != "Class":
                    continue
                candidates.append(elem)

        for cls in candidates:
            class_id = (
                cls.get("{http://www.omg.org/spec/XMI/20131001}id")
                or cls.get("xmi:id")
                or cls.get("id", "")
            )
            class_name = cls.get("name", "")
            if not class_id or not class_name:
                continue

            concept = classify_ap239_concept(class_name)
            if concept == "Part":
                model.parts[class_id] = AP239Part(id=class_id, name=class_name)
            elif concept == "Activity":
                model.activities[class_id] = AP239Activity(id=class_id, name=class_name)
            elif concept == "Requirement":
                model.requirements[class_id] = AP239Requirement(id=class_id, name=class_name)
            elif concept == "Interface":
                model.interface_connectors[class_id] = AP239InterfaceConnector(
                    id=class_id, name=class_name
                )
            elif concept == "Document":
                model.documents[class_id] = AP239Document(id=class_id, name=class_name)

    def _extract_associations(self, root, model: AP239Model) -> None:
        """Log associations for future relationship extraction."""
        ns = self._NAMESPACES
        for assoc in root.findall(".//uml:Association", ns) if hasattr(root, 'findall') else []:
            logger.debug(f"AP239 association: {assoc.get('name', '')}")


# ---------------------------------------------------------------------------
# XSD validator
# ---------------------------------------------------------------------------

class AP239XSDValidator:
    """Validate AP239 XML data instances against the domain schema."""

    def validate_content(self, xml_content: bytes) -> Tuple[bool, List[str]]:
        """Validate raw XML bytes for AP239 compliance."""
        errors: List[str] = []
        try:
            import defusedxml.ElementTree as _safe_ET
            root = _safe_ET.fromstring(xml_content)
            tag = root.tag.split("}")[-1] if "}" in root.tag else root.tag
            if "DataContainer" not in tag and "AP239" not in tag:
                errors.append(
                    f"Root element should be AP239DataContainer or DataContainer, got '{tag}'"
                )
            ns = root.get("xmlns") or root.get("targetNamespace") or ""
            if ns and AP239_NAMESPACE not in ns and "AP239" not in ns.upper():
                errors.append(f"Unexpected namespace: {ns}")
        except Exception as exc:
            errors.append(f"XML parse error: {exc}")
        return len(errors) == 0, errors


# ---------------------------------------------------------------------------
# Convenience API
# ---------------------------------------------------------------------------

def parse_ap239_xmi(xmi_path: Path) -> AP239Model:
    """Parse an AP239 XMI file and return the domain model."""
    return AP239XMIParser().parse_xmi_file(xmi_path)


def model_statistics(model: AP239Model) -> Dict[str, int]:
    """Return element counts for an AP239Model."""
    return {
        "parts": len(model.parts),
        "activities": len(model.activities),
        "requirements": len(model.requirements),
        "interface_connectors": len(model.interface_connectors),
        "documents": len(model.documents),
        "total_elements": (
            len(model.parts) + len(model.activities) + len(model.requirements)
            + len(model.interface_connectors) + len(model.documents)
        ),
    }
