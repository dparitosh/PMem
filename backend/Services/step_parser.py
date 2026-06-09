"""Lightweight STEP parser compatibility layer.

This module restores the parser API expected by service and engine modules.
It focuses on reliable entity extraction and conservative PMI defaults.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterator, List, Optional
import re
import xml.etree.ElementTree as ET

try:
    from .ap242_domain_model import (
        AP242_DOMAIN_MODEL_NAMESPACE,
        AP242_DOMAIN_MODEL_SCHEMA_TOKEN,
        is_ap242_domain_model_namespace,
    )
except ImportError:
    from ap242_domain_model import (  # type: ignore
        AP242_DOMAIN_MODEL_NAMESPACE,
        AP242_DOMAIN_MODEL_SCHEMA_TOKEN,
        is_ap242_domain_model_namespace,
    )


_ENTITY_RE = re.compile(r"^\s*#(\d+)\s*=\s*([A-Z0-9_]+)\s*\((.*)\)\s*$", re.IGNORECASE | re.DOTALL)
# Compound entity instance: #n = (ENTITY1(...) ENTITY2(...)) — ISO 10303-11 §12.4.3
_COMPOUND_ENTITY_RE = re.compile(r"^\s*#(\d+)\s*=\s*\((.+)\)\s*$", re.DOTALL)
_REF_RE = re.compile(r"#(\d+)")
# Matches STEP string literals ('' escape for embedded single quote)
_STEP_STR_RE = re.compile(r"'((?:[^']|'')*)'")  # from AP242 bom_mapper reference

# AP242 entity types where positional args are: ext_id, name, description
# Reference: ISO 10303-44 Part_definition_schema, Product_definition_schema
_AP242_NAMED_ENTITIES = frozenset([
    'PRODUCT', 'PRODUCT_DEFINITION', 'PRODUCT_DEFINITION_FORMATION',
    'PRODUCT_DEFINITION_FORMATION_WITH_SPECIFIED_SOURCE',
    'NEXT_ASSEMBLY_USAGE_OCCURRENCE', 'ASSEMBLY_COMPONENT_USAGE',
    'PRODUCT_RELATED_PRODUCT_CATEGORY',
])

_AP242_ENTITY_ALIASES = {
    # Part28/common XML token variants mapped to AP242 AIM dictionary names.
    "PRODUCTDEFINITION": "PRODUCT_DEFINITION",
    "PRODUCTDEFINITIONFORMATION": "PRODUCT_DEFINITION_FORMATION",
    "PRODUCTDEFINITIONFORMATIONWITHSPECIFIEDSOURCE": "PRODUCT_DEFINITION_FORMATION_WITH_SPECIFIED_SOURCE",
    "NEXTASSEMBLYUSAGEOCCURRENCE": "NEXT_ASSEMBLY_USAGE_OCCURRENCE",
    "ASSEMBLYCOMPONENTUSAGE": "ASSEMBLY_COMPONENT_USAGE",
    "REPRESENTATIONCONTEXT": "REPRESENTATION_CONTEXT",
    "GEOMETRICREPRESENTATIONCONTEXT": "GEOMETRIC_REPRESENTATION_CONTEXT",
    "APPLICATIONCONTEXT": "APPLICATION_CONTEXT",
    "PRODUCTDEFINITIONCONTEXT": "PRODUCT_DEFINITION_CONTEXT",
}


@functools.lru_cache(maxsize=4096)
def normalize_ap242_entity_type(entity_type: str) -> str:
    """Normalize STEP/Part28 entity names to AP242 dictionary-style tokens. Cached for performance."""
    raw = (entity_type or "").strip()
    if not raw:
        return ""

    with_underscores = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", raw)
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", with_underscores)
    collapsed = re.sub(r"_+", "_", cleaned).strip("_")
    upper = collapsed.upper()
    if not upper:
        return ""

    squashed = upper.replace("_", "")
    return _AP242_ENTITY_ALIASES.get(squashed, upper)


@dataclass
class StepFileMeta:
    format: str
    file_schema: Optional[str]
    file_name: str
    namespace: str = ""
    schema_location: str = ""
    schema_version: str = ""


@dataclass
class StepP21Entity:
    step_id: int
    entity_type: str
    raw_args: str
    ref_ids: List[int] = field(default_factory=list)


@dataclass
class StepGeometricTolerance:
    id: int
    tolerance_type: str = "UNKNOWN"
    name: str = ""
    description: str = ""
    magnitude: Optional[float] = None
    unit: str = ""
    datum_system_refs: List[int] = field(default_factory=list)
    toleranced_feature_refs: List[int] = field(default_factory=list)


@dataclass
class StepDatum:
    id: int
    label: str = ""
    datum_type: str = ""
    feature_refs: List[int] = field(default_factory=list)
    name: str = ""


@dataclass
class StepDimension:
    id: int
    dimension_type: str = ""
    name: str = ""
    description: str = ""
    nominal_value: Optional[float] = None
    upper_tolerance: Optional[float] = None
    lower_tolerance: Optional[float] = None
    unit: str = ""
    feature_refs: List[int] = field(default_factory=list)


@dataclass
class StepAnnotation:
    id: int
    annotation_type: str = ""
    text: str = ""
    name: str = ""
    presentation_refs: List[int] = field(default_factory=list)
    leader_refs: List[int] = field(default_factory=list)


@dataclass
class StepSurfaceFinish:
    id: int
    finish_type: str = ""
    roughness_average: Optional[float] = None
    roughness_max: Optional[float] = None
    unit: str = ""
    method: str = ""
    feature_refs: List[int] = field(default_factory=list)


@dataclass
class StepCadEntity:
    id: int
    entity_type: str
    external_id: str = ""
    name: str = ""
    description: str = ""
    ref_ids: List[int] = field(default_factory=list)


@dataclass
class StepPMIDocument:
    metadata: StepFileMeta
    entities: List[StepP21Entity]
    entity_map: Dict[int, StepP21Entity]
    geometric_tolerances: List[StepGeometricTolerance] = field(default_factory=list)
    datums: List[StepDatum] = field(default_factory=list)
    dimensions: List[StepDimension] = field(default_factory=list)
    annotations: List[StepAnnotation] = field(default_factory=list)
    surface_finishes: List[StepSurfaceFinish] = field(default_factory=list)
    cad_products: List[StepCadEntity] = field(default_factory=list)
    cad_representations: List[StepCadEntity] = field(default_factory=list)
    cad_topology: List[StepCadEntity] = field(default_factory=list)
    cad_geometry: List[StepCadEntity] = field(default_factory=list)


def extract_step_strings(raw_args: str) -> List[str]:
    """Extract STEP string literals from a raw_args string, unescaping '' → '.

    Canonical pattern from AP242 bom_mapper reference (requirements/src/engines/).
    Position semantics for named entities:
        [0] = external_id / ID string
        [1] = name
        [2] = description
    """
    return [m.replace("''", "'") for m in _STEP_STR_RE.findall(raw_args)]


def detect_step_format(file_path: Path) -> str:
    suffix = file_path.suffix.lower()
    if suffix == ".stpx":
        return "stpx"
    if suffix == ".xml":
        try:
            text = file_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return "p21"
        if "iso_10303_28" in text.lower():
            return "stpx"
    return "p21"


def parse_step_metadata(
    file_path: Path,
    _text: Optional[str] = None,
    _format: Optional[str] = None,
) -> StepFileMeta:
    fmt = _format or detect_step_format(file_path)
    schema = None
    try:
        text = _text if _text is not None else file_path.read_text(encoding="utf-8", errors="ignore")
        match = re.search(r"FILE_SCHEMA\s*\(\s*\('([^']+)'\)\s*\)", text, flags=re.IGNORECASE)
        if match:
            schema = match.group(1)
        elif fmt == "stpx":
            # ✅ SECURITY: use defusedxml for STPX schema extraction to prevent XXE
            import defusedxml.ElementTree as _DET
            root = _DET.fromstring(text)
            namespace = _namespace_uri(root.tag)
            schema_location = (
                root.attrib.get("{http://www.w3.org/2001/XMLSchema-instance}schemaLocation")
                or root.attrib.get("schemaLocation")
                or ""
            )
            schema_version = root.attrib.get("schemaVersion") or root.attrib.get("version") or ""
            schema = schema_version
            if is_ap242_domain_model_namespace(namespace) or AP242_DOMAIN_MODEL_NAMESPACE in schema_location:
                schema = AP242_DOMAIN_MODEL_SCHEMA_TOKEN
            elif namespace:
                schema = namespace.rstrip("/").rsplit("/", 1)[-1] or schema
            return StepFileMeta(
                format=fmt,
                file_schema=schema,
                file_name=file_path.name,
                namespace=namespace,
                schema_location=schema_location,
                schema_version=schema_version,
            )
    except OSError:
        pass
    except ET.ParseError:
        pass

    return StepFileMeta(
        format=fmt,
        file_schema=schema,
        file_name=file_path.name,
    )


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def _namespace_uri(tag: str) -> str:
    if tag.startswith("{") and "}" in tag:
        return tag[1:].split("}", 1)[0]
    return ""


def _extract_part21_data_records(text: str) -> List[str]:
    cleaned = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)

    upper = cleaned.upper()
    data_start = upper.find("DATA;")
    if data_start != -1:
        endsec = upper.find("ENDSEC;", data_start)
        if endsec != -1:
            cleaned = cleaned[data_start + len("DATA;"):endsec]
        else:
            cleaned = cleaned[data_start + len("DATA;"):]

    records: List[str] = []
    buf: List[str] = []
    depth = 0
    in_string = False
    i = 0

    while i < len(cleaned):
        ch = cleaned[i]

        if ch == "'":
            # STEP strings escape quote as two consecutive single quotes.
            if in_string and i + 1 < len(cleaned) and cleaned[i + 1] == "'":
                buf.append(ch)
                buf.append(cleaned[i + 1])
                i += 2
                continue
            in_string = not in_string
            buf.append(ch)
            i += 1
            continue

        if not in_string:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth = max(0, depth - 1)
            elif ch == ";" and depth == 0:
                record = "".join(buf).strip()
                if record:
                    records.append(record)
                buf = []
                i += 1
                continue

        buf.append(ch)
        i += 1

    return records


def _iter_part21_entities(file_path: Path, _text: Optional[str] = None) -> Iterator[StepP21Entity]:
    text = _text if _text is not None else file_path.read_text(encoding="utf-8", errors="ignore")
    for record in _extract_part21_data_records(text):
        match = _ENTITY_RE.match(record)
        if not match:
            # G-C: try compound entity instance form: #n = (ENTITY1(...) ENTITY2(...))
            m_compound = _COMPOUND_ENTITY_RE.match(record)
            if m_compound:
                step_id = int(m_compound.group(1))
                inner = m_compound.group(2)
                # Extract first entity type token from compound form
                first_m = re.match(r'\s*([A-Z][A-Z0-9_]*)\s*\(', inner, re.IGNORECASE)
                etype = normalize_ap242_entity_type(first_m.group(1)) if first_m else 'COMPOUND_ENTITY'
                yield StepP21Entity(
                    step_id=step_id,
                    entity_type=etype,
                    raw_args=inner[:500],
                    ref_ids=[int(v) for v in _REF_RE.findall(inner)],
                )
            continue

        step_id = int(match.group(1))
        entity_type = normalize_ap242_entity_type(match.group(2))
        raw_args = match.group(3).strip()
        ref_ids = [int(v) for v in _REF_RE.findall(raw_args)]
        yield StepP21Entity(
            step_id=step_id,
            entity_type=entity_type,
            raw_args=raw_args,
            ref_ids=ref_ids,
        )


def _iter_part28_entities(file_path: Path) -> Iterator[StepP21Entity]:
    import defusedxml.ElementTree as _DET   # ✅ SECURITY: XXE-safe replacement for stdlib ET
    tree = _DET.parse(str(file_path))
    root = tree.getroot()

    id_to_step: Dict[str, int] = {}
    next_step_id = 1

    for elem in root.iter():
        elem_id = elem.attrib.get("id")
        if elem_id and elem_id not in id_to_step:
            id_to_step[elem_id] = next_step_id
            next_step_id += 1

    for elem in root.iter():
        entity_type = normalize_ap242_entity_type(_local_name(elem.tag))
        if not entity_type:
            continue

        elem_id = elem.attrib.get("id")
        if elem_id and elem_id in id_to_step:
            step_id = id_to_step[elem_id]
        else:
            step_id = next_step_id
            next_step_id += 1

        raw_parts: List[str] = []
        ref_ids: List[int] = []

        for key, value in elem.attrib.items():
            local_key = _local_name(key)
            raw_parts.append(f"{local_key}={value}")

            tokens = re.split(r"[\s,]+", value.strip())
            for token in tokens:
                if not token:
                    continue
                if token in id_to_step:
                    ref_ids.append(id_to_step[token])
                    continue
                if token.startswith("#") and token[1:].isdigit():
                    ref_ids.append(int(token[1:]))

        text_value = (elem.text or "").strip()
        if text_value and len(list(elem)) == 0:
            raw_parts.append(f"text={text_value[:200]}")

        yield StepP21Entity(
            step_id=step_id,
            entity_type=entity_type,
            raw_args=", ".join(raw_parts),
            ref_ids=sorted(set(ref_ids)),
        )


def iter_part21_entities(file_path: Path) -> Iterator[StepP21Entity]:
    if detect_step_format(file_path) == "stpx":
        yield from _iter_part28_entities(file_path)
        return
    yield from _iter_part21_entities(file_path)


def _classify_cad_entity(entity: StepP21Entity) -> Optional[str]:
    et = entity.entity_type.upper()
    if et in {"PRODUCT", "PRODUCT_RELATED_PRODUCT_CATEGORY", "PRODUCT_CATEGORY"}:
        return "product"
    if "REPRESENTATION" in et:
        return "representation"
    if any(token in et for token in ("EDGE", "FACE", "SHELL", "TOPO")):
        return "topology"
    if any(token in et for token in ("POINT", "CURVE", "SURFACE", "GEOMETRIC")):
        return "geometry"
    return None


def _first_number(raw_args: str) -> Optional[float]:
    match = re.search(r"[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[Ee][-+]?\d+)?", raw_args or "")
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _classify_pmi_entity(entity: StepP21Entity) -> Optional[str]:
    et = entity.entity_type.upper()
    if "GEOMETRIC_TOLERANCE" in et or et.endswith("_TOLERANCE"):
        return "geometric_tolerance"
    if "DATUM" in et:
        return "datum"
    if "DIMENSION" in et or et in {"DIMENSIONAL_SIZE", "DIMENSIONAL_LOCATION"}:
        return "dimension"
    if "ANNOTATION" in et or "DRAUGHTING" in et:
        return "annotation"
    if "SURFACE_FINISH" in et or "SURFACE_TEXTURE" in et or "ROUGHNESS" in et:
        return "surface_finish"
    return None


def _cad_name_fields(entity: StepP21Entity) -> tuple[str, str, str]:
    strings = extract_step_strings(entity.raw_args)
    external_id = strings[0] if strings else ""
    name = strings[1] if len(strings) > 1 else external_id
    description = strings[2] if len(strings) > 2 else ""
    return external_id, name, description


def parse_step_with_pmi(file_path: Path) -> StepPMIDocument:
    fmt = detect_step_format(file_path)
    # Read file text once for p21 files (G19 — avoids 2× disk read on large STEP files)
    _p21_text: Optional[str] = (
        file_path.read_text(encoding="utf-8", errors="ignore") if fmt == "p21" else None
    )
    metadata = parse_step_metadata(file_path, _p21_text, _format=fmt)
    entities = list(
        _iter_part21_entities(file_path, _p21_text) if fmt == "p21"
        else iter_part21_entities(file_path)
    )
    entity_map = {entity.step_id: entity for entity in entities}

    cad_products: List[StepCadEntity] = []
    cad_representations: List[StepCadEntity] = []
    cad_topology: List[StepCadEntity] = []
    cad_geometry: List[StepCadEntity] = []
    geometric_tolerances: List[StepGeometricTolerance] = []
    datums: List[StepDatum] = []
    dimensions: List[StepDimension] = []
    annotations: List[StepAnnotation] = []
    surface_finishes: List[StepSurfaceFinish] = []

    for entity in entities:
        group = _classify_cad_entity(entity)
        if group:
            external_id, name, description = _cad_name_fields(entity)
            cad = StepCadEntity(
                id=entity.step_id,
                entity_type=entity.entity_type,
                external_id=external_id,
                name=name,
                description=description,
                ref_ids=list(entity.ref_ids),
            )
            if group == "product":
                cad_products.append(cad)
            elif group == "representation":
                cad_representations.append(cad)
            elif group == "topology":
                cad_topology.append(cad)
            elif group == "geometry":
                cad_geometry.append(cad)

        pmi_group = _classify_pmi_entity(entity)
        if not pmi_group:
            continue
        strings = extract_step_strings(entity.raw_args)
        label = strings[0] if strings else ""
        name = strings[1] if len(strings) > 1 else label
        description = strings[2] if len(strings) > 2 else ""
        number = _first_number(entity.raw_args)

        if pmi_group == "geometric_tolerance":
            geometric_tolerances.append(StepGeometricTolerance(
                id=entity.step_id,
                tolerance_type=entity.entity_type,
                name=name,
                description=description,
                magnitude=number,
                toleranced_feature_refs=list(entity.ref_ids),
            ))
        elif pmi_group == "datum":
            datums.append(StepDatum(
                id=entity.step_id,
                label=label,
                datum_type=entity.entity_type,
                feature_refs=list(entity.ref_ids),
                name=name,
            ))
        elif pmi_group == "dimension":
            dimensions.append(StepDimension(
                id=entity.step_id,
                dimension_type=entity.entity_type,
                name=name,
                description=description,
                nominal_value=number,
                feature_refs=list(entity.ref_ids),
            ))
        elif pmi_group == "annotation":
            annotations.append(StepAnnotation(
                id=entity.step_id,
                annotation_type=entity.entity_type,
                text=description or name or label,
                name=name,
                presentation_refs=list(entity.ref_ids),
            ))
        elif pmi_group == "surface_finish":
            surface_finishes.append(StepSurfaceFinish(
                id=entity.step_id,
                finish_type=entity.entity_type,
                roughness_average=number,
                feature_refs=list(entity.ref_ids),
            ))

    return StepPMIDocument(
        metadata=metadata,
        entities=entities,
        entity_map=entity_map,
        geometric_tolerances=geometric_tolerances,
        datums=datums,
        dimensions=dimensions,
        annotations=annotations,
        surface_finishes=surface_finishes,
        cad_products=cad_products,
        cad_representations=cad_representations,
        cad_topology=cad_topology,
        cad_geometry=cad_geometry,
    )


def get_pmi_summary(doc: StepPMIDocument) -> Dict[str, int | bool]:
    return {
        "total_entities": len(doc.entities),
        "has_pmi": bool(doc.geometric_tolerances or doc.datums or doc.dimensions or doc.annotations),
        "geometric_tolerances": len(doc.geometric_tolerances),
        "datums": len(doc.datums),
        "dimensions": len(doc.dimensions),
        "annotations": len(doc.annotations),
        "cad_products": len(doc.cad_products),
        "cad_representations": len(doc.cad_representations),
        "cad_topology": len(doc.cad_topology),
        "cad_geometry": len(doc.cad_geometry),
        "has_cad_semantics": bool(doc.cad_products or doc.cad_representations or doc.cad_topology or doc.cad_geometry),
    }
