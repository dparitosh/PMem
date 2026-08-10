"""Lightweight STEP parser compatibility layer.

This module restores the parser API expected by service and engine modules.
It focuses on reliable entity extraction and conservative PMI defaults.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterator, List, Optional
import logging
import re
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)

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

def _extract_compound_entity_types(inner: str) -> List[str]:
    """Return top-level entity names from a Part 21 compound entity instance."""
    types: List[str] = []
    depth = 0
    token_start: Optional[int] = None
    i = 0
    while i < len(inner):
        ch = inner[i]
        if ch == "'":
            i += 1
            while i < len(inner):
                if inner[i] == "'":
                    if i + 1 < len(inner) and inner[i + 1] == "'":
                        i += 2
                        continue
                    break
                i += 1
        elif ch == "(":
            if depth == 0 and token_start is not None:
                raw_name = inner[token_start:i].strip()
                if raw_name:
                    normalized = normalize_ap242_entity_type(raw_name)
                    if normalized:
                        types.append(normalized)
                token_start = None
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif depth == 0:
            if token_start is None and (ch.isalpha() or ch == "_"):
                token_start = i
            elif token_start is not None and not (ch.isalnum() or ch == "_"):
                token_start = None
        i += 1

    return types


def _entity_type_candidates(entity: "StepP21Entity") -> List[str]:
    """Primary plus compound AP242 entity types, preserving order and uniqueness."""
    candidates = [entity.entity_type, *getattr(entity, "compound_entity_types", [])]
    seen = set()
    ordered: List[str] = []
    for candidate in candidates:
        normalized = normalize_ap242_entity_type(candidate)
        if normalized and normalized not in seen:
            seen.add(normalized)
            ordered.append(normalized)
    return ordered
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
    compound_entity_types: List[str] = field(default_factory=list)
    attributes: Dict[str, str] = field(default_factory=dict)
    text_value: str = ""
    source_identifier: str = ""
    source_identifier_kind: str = ""
    unresolved_refs: List[str] = field(default_factory=list)
    parent_step_id: Optional[int] = None


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
    feature_refs: List[int] = field(default_factory=list)
    view_refs: List[int] = field(default_factory=list)


@dataclass
class StepGraphicPresentation:
    id: int
    presentation_type: str = ""
    annotation_refs: List[int] = field(default_factory=list)
    geometry_refs: List[int] = field(default_factory=list)
    view_refs: List[int] = field(default_factory=list)
    style_refs: List[int] = field(default_factory=list)


@dataclass
class StepSavedView:
    id: int
    view_type: str = ""
    name: str = ""
    annotation_refs: List[int] = field(default_factory=list)
    geometry_refs: List[int] = field(default_factory=list)
    presentation_refs: List[int] = field(default_factory=list)


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
    graphic_presentations: List[StepGraphicPresentation] = field(default_factory=list)
    saved_views: List[StepSavedView] = field(default_factory=list)
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
        text_lower = text.lower()
        if (
            "iso_10303_28" in text_lower
            or "tech/xml-schema/domain_model" in text_lower
            or "tech/xml-schema/bo_model" in text_lower
            or "standards.iso.org/iso/ts/10303/" in text_lower
            or "xmlns=\"urn:iso:std:iso:10303:" in text_lower
        ):
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
            # ✅ SECURITY: use defusedxml iterparse for STPX schema extraction to prevent XXE
            import defusedxml.ElementTree as _DET
            root = None
            for _event, _elem in _DET.iterparse(str(file_path), events=("start",)):
                root = _elem
                break
            if root is None:
                raise ET.ParseError("STPX root element missing")
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
                compound_types = _extract_compound_entity_types(inner)
                etype = compound_types[0] if compound_types else 'COMPOUND_ENTITY'
                yield StepP21Entity(
                    step_id=step_id,
                    entity_type=etype,
                    raw_args=inner[:500],
                    ref_ids=[int(v) for v in _REF_RE.findall(inner)],
                    compound_entity_types=compound_types,
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

    def _tokenize_refs(value: str) -> List[str]:
        return [token for token in re.split(r"[\s,]+", (value or "").strip()) if token]

    def _is_ref_key(key: str) -> bool:
        lower = key.lower()
        return lower.endswith("ref") or lower.endswith("refs") or lower in {"href", "idref", "uidref", "idcontextref"}

    alias_to_step: Dict[str, int] = {}
    duplicate_aliases: Dict[str, int] = {}

    # First pass: assign deterministic synthetic step ids to every element in
    # document order and collect all local aliases so forward refs resolve.
    next_step_id = 1
    for event, elem in _DET.iterparse(str(file_path), events=("start",)):
        if event != "start":
            continue
        current_step_id = next_step_id
        next_step_id += 1
        for alias_key in ("id", "uid"):
            alias_value = (elem.attrib.get(alias_key) or "").strip()
            if not alias_value:
                continue
            if alias_value in alias_to_step:
                duplicate_aliases[alias_value] = duplicate_aliases.get(alias_value, 1) + 1
            else:
                alias_to_step[alias_value] = current_step_id
        elem.clear()

    next_step_id = 1
    stack: List[int] = []

    for event, elem in _DET.iterparse(str(file_path), events=("start", "end")):
        if event == "start":
            current_step_id = next_step_id
            next_step_id += 1
            stack.append(current_step_id)
            continue

        step_id = stack.pop() if stack else next_step_id
        entity_type = normalize_ap242_entity_type(_local_name(elem.tag))
        if not entity_type:
            elem.clear()
            continue

        attrs = {_local_name(key): value for key, value in elem.attrib.items()}
        raw_parts: List[str] = []
        ref_ids: List[int] = []
        unresolved_refs: List[str] = []
        for key, value in attrs.items():
            raw_parts.append(f"{key}={value}")
            if not _is_ref_key(key):
                continue
            for token in _tokenize_refs(value):
                if token in alias_to_step:
                    ref_ids.append(alias_to_step[token])
                elif token.startswith("#") and token[1:].isdigit():
                    ref_ids.append(int(token[1:]))
                else:
                    unresolved_refs.append(token)

        text_value = (elem.text or "").strip()
        if text_value and len(list(elem)) == 0:
            raw_parts.append(f"text={text_value[:200]}")

        source_identifier = (attrs.get("id") or attrs.get("uid") or "").strip()
        source_identifier_kind = "id" if attrs.get("id") else ("uid" if attrs.get("uid") else "synthetic")
        parent_step_id = stack[-1] if stack else None

        yield StepP21Entity(
            step_id=step_id,
            entity_type=entity_type,
            raw_args=", ".join(raw_parts),
            ref_ids=sorted(set(ref_ids)),
            attributes=attrs,
            text_value=text_value[:1000],
            source_identifier=source_identifier,
            source_identifier_kind=source_identifier_kind,
            unresolved_refs=sorted(set(unresolved_refs)),
            parent_step_id=parent_step_id,
        )
        elem.clear()

    if duplicate_aliases:
        sample = list(duplicate_aliases.items())[:10]
        logger.warning("STPX duplicate alias identifiers detected: %s", sample)


def iter_part21_entities(file_path: Path) -> Iterator[StepP21Entity]:
    if detect_step_format(file_path) == "stpx":
        yield from _iter_part28_entities(file_path)
        return
    yield from _iter_part21_entities(file_path)


def _classify_cad_entity(entity: StepP21Entity) -> Optional[str]:
    for et in _entity_type_candidates(entity):
        if (
            "TOLERANCE" in et
            or "DATUM" in et
            or "DIMENSION" in et
            or "ANNOTATION" in et
            or "DRAUGHTING" in et
            or "SURFACE_FINISH" in et
            or "SURFACE_TEXTURE" in et
            or "ROUGHNESS" in et
        ):
            continue
        if et in {
            "PRODUCT",
            "PRODUCT_RELATED_PRODUCT_CATEGORY",
            "PRODUCT_CATEGORY",
            # AP242 Part28 / BO model tokens
            "PART",
            "PART_VERSION",
        }:
            return "product"
        if et in {"PART_VIEW", "VIEW", "VIEWS", "GEOMETRIC_MODEL"} or "REPRESENTATION" in et:
            return "representation"
        if et in {"SHAPE_ASPECT", "SHAPE_ASPECT_RELATIONSHIP"} or "FEATURE" in et:
            return "feature"
        if "SHAPE" in et:
            return "shape"
        if et in {"OCCURRENCE", "VIEW_OCCURRENCE_RELATIONSHIP"} or any(token in et for token in ("EDGE", "FACE", "SHELL", "TOPO")):
            return "topology"
        if et in {"PLACEMENT", "CARTESIAN_TRANSFORMATION", "ROTATION_MATRIX", "TRANSLATION_VECTOR"} or any(token in et for token in ("POINT", "CURVE", "SURFACE", "GEOMETRIC")):
            return "geometry"
    return None


def _first_number(raw_args: str) -> Optional[float]:
    cleaned = re.sub(r"'(?:[^']|'')*'", " ", raw_args or "")
    cleaned = re.sub(r"#\d+", " ", cleaned)
    match = re.search(r"[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[Ee][-+]?\d+)?", cleaned)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _measure_number(
    entity: StepP21Entity,
    entity_map: Dict[int, StepP21Entity],
    visited: Optional[set[int]] = None,
) -> Optional[float]:
    """Return a real AP242 measure, avoiding quoted labels and STEP reference ids."""
    visited = visited or set()
    if entity.step_id in visited:
        return None
    visited.add(entity.step_id)

    direct = _first_number(entity.raw_args)
    if direct is not None and (
        "MEASURE" in entity.entity_type
        or "VALUE" in entity.entity_type
        or entity.entity_type in {"REAL", "INTEGER", "NUMBER"}
    ):
        return direct

    for ref_id in entity.ref_ids:
        ref = entity_map.get(ref_id)
        if not ref:
            continue
        if (
            "MEASURE" in ref.entity_type
            or "VALUE" in ref.entity_type
            or ref.entity_type in {"REAL", "INTEGER", "NUMBER"}
        ):
            resolved = _measure_number(ref, entity_map, visited)
            if resolved is not None:
                return resolved
    return direct


def _tolerance_bounds(entity: StepP21Entity, entity_map: Dict[int, StepP21Entity]) -> tuple[Optional[float], Optional[float]]:
    """Resolve AP242 TOLERANCE_VALUE lower/upper bounds from referenced measures."""
    if entity.entity_type != "TOLERANCE_VALUE":
        return None, None
    values: List[float] = []
    for ref_id in entity.ref_ids:
        ref = entity_map.get(ref_id)
        if not ref:
            continue
        value = _measure_number(ref, entity_map)
        if value is not None:
            values.append(value)
    if not values:
        return None, None
    if len(values) == 1:
        return values[0], values[0]
    return values[0], values[1]


def _apply_dimension_tolerances(dimensions: List[StepDimension], entity_map: Dict[int, StepP21Entity]) -> None:
    """Attach PLUS_MINUS_TOLERANCE/TOLERANCE_VALUE bounds to the referenced dimension."""
    dimensions_by_id = {dim.id: dim for dim in dimensions}
    for entity in entity_map.values():
        if entity.entity_type != "PLUS_MINUS_TOLERANCE":
            continue
        tolerance_ref = next((ref_id for ref_id in entity.ref_ids if entity_map.get(ref_id, None) and entity_map[ref_id].entity_type == "TOLERANCE_VALUE"), None)
        dimension_ref = next((ref_id for ref_id in entity.ref_ids if ref_id in dimensions_by_id), None)
        if tolerance_ref is None or dimension_ref is None:
            continue
        lower, upper = _tolerance_bounds(entity_map[tolerance_ref], entity_map)
        dim = dimensions_by_id[dimension_ref]
        if lower is not None:
            dim.lower_tolerance = lower
        if upper is not None:
            dim.upper_tolerance = upper


def _refs_matching(entity: StepP21Entity, entity_map: Dict[int, StepP21Entity], markers: tuple[str, ...]) -> List[int]:
    """Return references whose resolved STEP type matches semantic markers."""
    matches: List[int] = []
    for ref_id in entity.ref_ids:
        ref = entity_map.get(ref_id)
        ref_types = _entity_type_candidates(ref) if ref else []
        if any(any(marker in ref_type for marker in markers) for ref_type in ref_types):
            matches.append(ref_id)
    return sorted(set(matches))


def _typed_pmi_refs(entity: StepP21Entity, entity_map: Dict[int, StepP21Entity]) -> Dict[str, List[int]]:
    """Classify broad STEP references without pretending to fully infer EXPRESS positions."""
    datum_refs = _refs_matching(entity, entity_map, ("DATUM",))
    leader_refs = _refs_matching(entity, entity_map, ("LEADER",))
    feature_refs = _refs_matching(entity, entity_map, (
        "SHAPE_ASPECT", "FEATURE", "FACE", "EDGE", "VERTEX", "SURFACE", "CURVE", "POINT", "GEOMETRY",
        "PRODUCT_DEFINITION", "PRODUCT", "REPRESENTATION_ITEM",
    ))
    return {
        "datum": datum_refs,
        "feature": [ref_id for ref_id in feature_refs if ref_id not in datum_refs and ref_id not in leader_refs],
        "presentation": _refs_matching(entity, entity_map, (
            "ANNOTATION", "DRAUGHTING", "PRESENTATION", "STYLED_ITEM", "TEXT_LITERAL", "GEOMETRIC_CURVE_SET",
        )),
        "leader": leader_refs,
        "view": _refs_matching(entity, entity_map, (
            "VIEW", "ANNOTATION_PLANE", "REPRESENTATION_CONTEXT", "CAMERA", "PRESENTATION_REPRESENTATION",
        )),
        "style": _refs_matching(entity, entity_map, ("STYLE", "PRESENTATION_LAYER", "PRESENTATION_STYLE")),
    }


def _is_graphic_presentation_entity(entity: StepP21Entity) -> bool:
    return any(marker in entity_type for entity_type in _entity_type_candidates(entity) for marker in (
        "ANNOTATION_OCCURRENCE", "DRAUGHTING_CALLOUT", "LEADER", "ANNOTATION_PLANE",
        "PRESENTATION_REPRESENTATION", "PRESENTATION_LAYER", "PRESENTATION_STYLE",
    ))


def _is_saved_view_entity(entity: StepP21Entity) -> bool:
    return any(entity_type in {"VIEW", "PRESENTATION_VIEW", "ANNOTATION_PLANE"} for entity_type in _entity_type_candidates(entity))


def _classify_pmi_entity(entity: StepP21Entity) -> Optional[str]:
    for et in _entity_type_candidates(entity):
        if et == "PLUS_MINUS_TOLERANCE" or et == "TOLERANCE_VALUE":
            return "dimension_tolerance"
        if "GEOMETRIC_TOLERANCE" in et or (et.endswith("_TOLERANCE") and et != "PLUS_MINUS_TOLERANCE"):
            return "geometric_tolerance"
        if "DATUM" in et:
            return "datum"
        if "DIMENSION" in et or et in {"DIMENSIONAL_SIZE", "DIMENSIONAL_LOCATION", "ANGULAR_LOCATION"}:
            return "dimension"
        if (
            "ANNOTATION" in et
            or "DRAUGHTING" in et
            or "CALLOUT" in et
            or "TEXT_LITERAL" in et
            or "LEADER" in et
            or "STYLED_ITEM" in et
            or et in {"PRESENTATION_STYLE_ASSIGNMENT", "PRESENTATION_LAYER_ASSIGNMENT"}
        ):
            return "annotation"
        if "SURFACE_FINISH" in et or "SURFACE_TEXTURE" in et or "ROUGHNESS" in et:
            return "surface_finish"
    return None


def classify_step_semantic_role(entity: StepP21Entity) -> Optional[str]:
    """Return the import-facing AP242 semantic role for STEP/STPX entities."""
    return _classify_pmi_entity(entity) or _classify_cad_entity(entity)


def _cad_name_fields(entity: StepP21Entity) -> tuple[str, str, str]:
    strings = extract_step_strings(entity.raw_args)
    attrs = getattr(entity, "attributes", {}) or {}
    source_identifier = getattr(entity, "source_identifier", "") or ""
    external_id = strings[0] if strings else (source_identifier or attrs.get("id") or attrs.get("uid") or "")
    name = strings[1] if len(strings) > 1 else (
        attrs.get("name")
        or attrs.get("Name")
        or attrs.get("label")
        or attrs.get("title")
        or external_id
    )
    description = strings[2] if len(strings) > 2 else ""
    return external_id, name, description


def step_entity_display_fields(entity: StepP21Entity) -> tuple[str, str, str]:
    """Return stable external id, display name, and description for import rows."""
    return _cad_name_fields(entity)


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
    graphic_presentations: List[StepGraphicPresentation] = []
    saved_views: List[StepSavedView] = []
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

        typed_refs = _typed_pmi_refs(entity, entity_map)
        if _is_graphic_presentation_entity(entity):
            graphic_presentations.append(StepGraphicPresentation(
                id=entity.step_id,
                presentation_type=entity.entity_type,
                annotation_refs=typed_refs["presentation"],
                geometry_refs=typed_refs["feature"],
                view_refs=typed_refs["view"],
                style_refs=typed_refs["style"],
            ))
        if _is_saved_view_entity(entity):
            strings_for_view = extract_step_strings(entity.raw_args)
            saved_views.append(StepSavedView(
                id=entity.step_id,
                view_type=entity.entity_type,
                name=strings_for_view[1] if len(strings_for_view) > 1 else (strings_for_view[0] if strings_for_view else ""),
                annotation_refs=typed_refs["presentation"],
                geometry_refs=typed_refs["feature"],
                presentation_refs=typed_refs["presentation"] + typed_refs["style"],
            ))

        pmi_group = _classify_pmi_entity(entity)
        if not pmi_group:
            continue
        strings = extract_step_strings(entity.raw_args)
        label = strings[0] if strings else ""
        name = strings[1] if len(strings) > 1 else label
        description = strings[2] if len(strings) > 2 else ""
        number = _measure_number(entity, entity_map)

        if pmi_group == "geometric_tolerance":
            geometric_tolerances.append(StepGeometricTolerance(
                id=entity.step_id,
                tolerance_type=entity.entity_type,
                name=name,
                description=description,
                magnitude=number,
                datum_system_refs=typed_refs["datum"],
                toleranced_feature_refs=typed_refs["feature"],
            ))
        elif pmi_group == "datum":
            datums.append(StepDatum(
                id=entity.step_id,
                label=label,
                datum_type=entity.entity_type,
                feature_refs=typed_refs["feature"],
                name=name,
            ))
        elif pmi_group == "dimension":
            dimensions.append(StepDimension(
                id=entity.step_id,
                dimension_type=entity.entity_type,
                name=name,
                description=description,
                nominal_value=number,
                feature_refs=typed_refs["feature"],
            ))
        elif pmi_group == "dimension_tolerance":
            continue
        elif pmi_group == "annotation":
            annotations.append(StepAnnotation(
                id=entity.step_id,
                annotation_type=entity.entity_type,
                text=description or name or label,
                name=name,
                presentation_refs=typed_refs["presentation"],
                leader_refs=typed_refs["leader"],
                feature_refs=typed_refs["feature"],
                view_refs=typed_refs["view"],
            ))
        elif pmi_group == "surface_finish":
            surface_finishes.append(StepSurfaceFinish(
                id=entity.step_id,
                finish_type=entity.entity_type,
                roughness_average=number,
                feature_refs=typed_refs["feature"],
            ))

    _apply_dimension_tolerances(dimensions, entity_map)

    return StepPMIDocument(
        metadata=metadata,
        entities=entities,
        entity_map=entity_map,
        geometric_tolerances=geometric_tolerances,
        datums=datums,
        dimensions=dimensions,
        annotations=annotations,
        graphic_presentations=graphic_presentations,
        saved_views=saved_views,
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
        "graphic_presentations": len(doc.graphic_presentations),
        "saved_views": len(doc.saved_views),
        "cad_products": len(doc.cad_products),
        "cad_representations": len(doc.cad_representations),
        "cad_topology": len(doc.cad_topology),
        "cad_geometry": len(doc.cad_geometry),
        "has_cad_semantics": bool(doc.cad_products or doc.cad_representations or doc.cad_topology or doc.cad_geometry),
    }



