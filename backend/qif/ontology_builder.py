"""Pure QIF XSD inspection and ontology construction functions."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from defusedxml import ElementTree as ET

XS = "{http://www.w3.org/2001/XMLSchema}"


@dataclass(frozen=True)
class SchemaTerm:
    name: str
    kind: str
    source: str
    namespace: str = ""
    documentation: str = ""
    base: str = ""
    value_type: str = ""
    min_occurs: str = ""
    max_occurs: str = ""


def _documentation(node) -> str:
    values = [" ".join((item.text or "").split()) for item in node.findall(f".//{XS}documentation")]
    return " ".join(value for value in values if value)


def _local_name(value: str) -> str:
    return (value or "").split(":")[-1]


def inspect_schema_set(paths: Iterable[Path]) -> dict:
    """Read a set of trusted XSD files without resolving remote resources."""
    terms: list[SchemaTerm] = []
    references: list[dict[str, str]] = []
    source_files: list[str] = []
    errors: list[dict[str, str]] = []

    for path in sorted({Path(item) for item in paths}, key=lambda item: item.name.lower()):
        source_files.append(path.name)
        try:
            root = ET.parse(path).getroot()
        except Exception as exc:
            errors.append({"file": path.name, "error": str(exc)})
            continue
        target_namespace = (root.get("targetNamespace") or "").strip()

        for ref in root.findall(f"{XS}include") + root.findall(f"{XS}import"):
            location = (ref.get("schemaLocation") or "").strip()
            if location:
                references.append({"source": path.name, "reference": location, "kind": ref.tag.rsplit("}", 1)[-1]})

        for kind, tag in (("complex_type", "complexType"), ("simple_type", "simpleType"), ("element", "element")):
            for node in root.findall(f"{XS}{tag}"):
                name = (node.get("name") or "").strip()
                if not name:
                    continue
                extension = node.find(f".//{XS}extension")
                restriction = node.find(f".//{XS}restriction")
                parent_type = extension if extension is not None else restriction
                base = parent_type.get("base", "") if parent_type is not None else ""
                terms.append(SchemaTerm(
                    name=name, kind=kind, source=path.name, namespace=target_namespace,
                    documentation=_documentation(node), base=_local_name(base), value_type=_local_name(node.get("type", "")),
                ))

        for owner in root.findall(f"{XS}complexType"):
            owner_name = (owner.get("name") or "").strip()
            if not owner_name:
                continue
            for node in owner.findall(f".//{XS}attribute") + owner.findall(f".//{XS}element"):
                name = (node.get("name") or node.get("ref") or "").strip()
                if name:
                    terms.append(SchemaTerm(
                        name=_local_name(name), kind="property", source=path.name, namespace=target_namespace,
                        documentation=_documentation(node), base=owner_name,
                        value_type=_local_name(node.get("type", "")), min_occurs=node.get("minOccurs", "1"), max_occurs=node.get("maxOccurs", "1"),
                    ))

    # Child properties with the same local name remain distinct when they belong
    # to different owner types in the same XSD document.
    unique_terms = {
        (term.name, term.kind, term.source, term.base, term.value_type): term
        for term in terms
    }
    return {
        "source_files": source_files,
        "terms": list(unique_terms.values()),
        "references": references,
        "errors": errors,
    }


def validate_schema_set(inspection: dict, paths: Iterable[Path]) -> dict:
    """Validate upload closure and report actionable schema-set quality findings."""
    by_name: dict[str, list[Path]] = {}
    namespaces: set[str] = set()
    for path in paths:
        path = Path(path)
        by_name.setdefault(path.name.lower(), []).append(path)
        try:
            root = ET.parse(path).getroot()
            if root.get("targetNamespace"):
                namespaces.add(root.get("targetNamespace"))
        except Exception:
            pass

    errors = list(inspection.get("errors", []))
    warnings: list[dict[str, str]] = []
    resolved: list[dict[str, str]] = []
    for reference in inspection.get("references", []):
        location = reference["reference"]
        if location.startswith(("http://", "https://")):
            warnings.append({"source": reference["source"], "message": f"External schema reference is not fetched: {location}"})
            continue
        candidate = Path(location).name.lower()
        matches = by_name.get(candidate, [])
        if len(matches) == 1:
            resolved.append({**reference, "resolved_to": matches[0].name})
        elif len(matches) > 1:
            errors.append({"file": reference["source"], "error": f"Ambiguous schema reference: {location}"})
        else:
            errors.append({"file": reference["source"], "error": f"Missing included/imported schema: {location}"})

    duplicate_terms: dict[tuple[str, str], set[str]] = {}
    for term in inspection.get("terms", []):
        duplicate_terms.setdefault((term.name, term.kind), set()).add(term.source)
    duplicate_count = sum(1 for sources in duplicate_terms.values() if len(sources) > 1)
    if duplicate_count:
        warnings.append({"message": f"{duplicate_count} repeated term names were retained with source provenance."})

    # Compile each root schema using lxml/libxml2 when Semantica's installed
    # runtime provides it.  This catches W3C XSD grammar violations in addition
    # to the safe structural checks below.  The fallback keeps the service
    # operable in deliberately minimal local environments.
    compiler_available = False
    try:
        from lxml import etree as lxml_etree
        compiler_available = True
    except ImportError:
        lxml_etree = None
    locally_referenced = {Path(item["reference"]).name.lower() for item in inspection.get("references", []) if not item["reference"].startswith(("http://", "https://"))}
    roots = [Path(path) for path in paths if Path(path).name.lower() not in locally_referenced] or [Path(path) for path in paths]
    schema_validated = 0
    for root_path in roots:
        try:
            document = ET.parse(root_path).getroot()
            if document.tag != f"{XS}schema":
                raise ValueError("Root element is not xs:schema")
            if lxml_etree is not None:
                lxml_etree.XMLSchema(lxml_etree.parse(str(root_path)))
            schema_validated += 1
        except (OSError, ET.ParseError, ValueError) as exc:
            errors.append({"file": root_path.name, "error": f"XSD structural validation failed: {exc}"})
        except Exception as exc:
            errors.append({"file": root_path.name, "error": f"XSD grammar compilation failed: {exc}"})
    if not compiler_available:
        warnings.append({"message": "XSD validation is structural because lxml/libxml2 is unavailable; deploy the Semantica runtime image for full W3C grammar compilation."})
    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "resolved_references": resolved,
        "reference_count": len(inspection.get("references", [])),
        "namespace_count": len(namespaces),
        "namespaces": sorted(namespaces),
        "duplicate_term_groups": duplicate_count,
        "schema_documents_validated": schema_validated,
        "xsd_grammar_compiler": "lxml/libxml2" if compiler_available else "structural-fallback",
    }


def build_ontology_turtle(inspection: dict, prefix: str) -> tuple[bytes, dict]:
    """Create a reusable RDF/OWL artifact through the Semantica engine."""
    try:
        from ..ontology_service.semantica_adapter import semantica
    except ImportError:  # pragma: no cover - standalone script mode
        from ontology_service.semantica_adapter import semantica
    return semantica.generate_from_xsd_inspection(inspection, prefix)
