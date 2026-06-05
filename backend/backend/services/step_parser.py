"""Lightweight STEP parser compatibility layer.

This module restores the parser API expected by service and engine modules.
It focuses on reliable entity extraction and conservative PMI defaults.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterator, List, Optional
import re
import xml.etree.ElementTree as ET


_ENTITY_RE = re.compile(r"^\s*#(\d+)\s*=\s*([A-Z0-9_]+)\s*\((.*)\)\s*$", re.IGNORECASE | re.DOTALL)
_REF_RE = re.compile(r"#(\d+)")

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


def normalize_ap242_entity_type(entity_type: str) -> str:
    """Normalize STEP/Part28 entity names to AP242 dictionary-style tokens."""
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


def parse_step_metadata(file_path: Path) -> StepFileMeta:
    schema = None
    try:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
        match = re.search(r"FILE_SCHEMA\s*\(\s*\('([^']+)'\)\s*\)", text, flags=re.IGNORECASE)
        if match:
            schema = match.group(1)
        elif detect_step_format(file_path) == "stpx":
            root = ET.fromstring(text)
            schema = root.attrib.get("schemaVersion") or root.attrib.get("version")
    except OSError:
        pass
    except ET.ParseError:
        pass

    return StepFileMeta(
        format=detect_step_format(file_path),
        file_schema=schema,
        file_name=file_path.name,
    )


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


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


def _iter_part21_entities(file_path: Path) -> Iterator[StepP21Entity]:
    text = file_path.read_text(encoding="utf-8", errors="ignore")
    for record in _extract_part21_data_records(text):
        match = _ENTITY_RE.match(record)
        if not match:
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
    tree = ET.parse(file_path)
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
    if et.startswith("PRODUCT"):
        return "product"
    if "REPRESENTATION" in et:
        return "representation"
    if any(token in et for token in ("EDGE", "FACE", "SHELL", "TOPO")):
        return "topology"
    if any(token in et for token in ("POINT", "CURVE", "SURFACE", "GEOMETRIC")):
        return "geometry"
    return None


def parse_step_with_pmi(file_path: Path) -> StepPMIDocument:
    metadata = parse_step_metadata(file_path)
    entities = list(iter_part21_entities(file_path))
    entity_map = {entity.step_id: entity for entity in entities}

    cad_products: List[StepCadEntity] = []
    cad_representations: List[StepCadEntity] = []
    cad_topology: List[StepCadEntity] = []
    cad_geometry: List[StepCadEntity] = []

    for entity in entities:
        group = _classify_cad_entity(entity)
        if not group:
            continue
        cad = StepCadEntity(
            id=entity.step_id,
            entity_type=entity.entity_type,
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

    return StepPMIDocument(
        metadata=metadata,
        entities=entities,
        entity_map=entity_map,
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
