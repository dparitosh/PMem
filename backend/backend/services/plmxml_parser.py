"""Lightweight PLMXML parser compatibility layer.

This module extracts a practical PLMXML subset into stable dataclasses used by
processing and serialization services. The coverage is intentionally focused on
the constructs that occur in local schemas and sample payloads.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List
import xml.etree.ElementTree as ET


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


@dataclass
class PlmxmlPart:
    id: str
    name: str = ""
    part_number: str = ""
    revision: str = ""
    description: str = ""
    part_type: str = ""
    master_ref: str = ""
    user_data_refs: List[str] = field(default_factory=list)
    properties: Dict[str, str] = field(default_factory=dict)


@dataclass
class PlmxmlProductView:
    id: str
    name: str = ""
    view_type: str = ""
    root_refs: List[str] = field(default_factory=list)
    product_ref: str = ""
    structure_type: str = ""
    properties: Dict[str, str] = field(default_factory=dict)


@dataclass
class PlmxmlProductInstance:
    id: str
    name: str = ""
    part_ref: str = ""
    transform_ref: str = ""
    parent_ref: str = ""
    quantity: int = 1
    occurrence_refs: List[str] = field(default_factory=list)
    user_data_refs: List[str] = field(default_factory=list)
    application_refs: List[str] = field(default_factory=list)
    properties: Dict[str, str] = field(default_factory=dict)


@dataclass
class PlmxmlProcess:
    id: str
    name: str = ""
    process_type: str = ""
    description: str = ""
    time_required: float | None = None
    resources: List[str] = field(default_factory=list)
    properties: Dict[str, str] = field(default_factory=dict)


@dataclass
class PlmxmlProcessView:
    id: str
    name: str = ""
    root_process_refs: List[str] = field(default_factory=list)
    product_refs: List[str] = field(default_factory=list)
    properties: Dict[str, str] = field(default_factory=dict)


@dataclass
class PlmxmlProcessInstance:
    id: str
    process_ref: str = ""
    predecessor_refs: List[str] = field(default_factory=list)
    product_instance_refs: List[str] = field(default_factory=list)
    properties: Dict[str, str] = field(default_factory=dict)


@dataclass
class PlmxmlChangeNotice:
    id: str
    name: str = ""
    change_type: str = ""
    status: str = ""
    description: str = ""
    date: str = ""
    author: str = ""
    affected_items: List[str] = field(default_factory=list)
    properties: Dict[str, str] = field(default_factory=dict)


@dataclass
class PlmxmlRevision:
    id: str
    revision_id: str = ""
    base_ref: str = ""
    revision_type: str = ""
    date: str = ""
    description: str = ""
    change_notice_refs: List[str] = field(default_factory=list)
    properties: Dict[str, str] = field(default_factory=dict)


@dataclass
class PlmxmlTransform:
    id: str
    matrix: List[float] = field(default_factory=list)


@dataclass
class PlmxmlUserData:
    id: str
    type: str = ""
    title: str = ""
    values: Dict[str, str] = field(default_factory=dict)


@dataclass
class PlmxmlExternalFile:
    id: str
    name: str = ""
    location: str = ""
    format: str = ""
    mime_type: str = ""
    properties: Dict[str, str] = field(default_factory=dict)


@dataclass
class PlmxmlDocumentItem:
    id: str
    name: str = ""
    document_type: str = ""
    description: str = ""
    revision: str = ""
    external_file_refs: List[str] = field(default_factory=list)
    user_data_refs: List[str] = field(default_factory=list)
    properties: Dict[str, str] = field(default_factory=dict)


@dataclass
class PlmxmlRequirement:
    """Teamcenter Requirement (R-layer of RFLP / SysML Requirement)."""
    id: str
    name: str = ""
    catalogue_id: str = ""
    revision: str = ""
    revision_id: str = ""  # from RequirementRevision
    master_ref: str = ""
    body_text: str = ""
    last_mod_date: str = ""
    object_string: str = ""
    dataset_ref: str = ""
    user_data_refs: List[str] = field(default_factory=list)
    properties: Dict[str, str] = field(default_factory=dict)


_RFLP_LAYER_MAP: Dict[str, str] = {
    # Requirements
    "Requirement": "R",
    "RequirementRevision": "R",
    # Functional (system-level / logical / physical functions)
    "Sys0SystemFunc": "F",
    "Sys0SystemFuncRevision": "F",
    "Sys0LogicalFunc": "F",
    "Sys0LogicalFuncRevision": "F",
    "Sys0PhysicalFunc": "F",
    "Sys0PhysicalFuncRevision": "F",
    # Logical components
    "Sys0LogicalComp": "L",
    "Sys0LogicalCompRevision": "L",
    # Physical components / nodes
    "Sys0PhysNodeComp": "P",
    "Sys0PhysNodeCompRevision": "P",
    # Items (physical parts in EBOM)
    "Item": "P",
    "ItemRevision": "P",
}


def _rflp_layer(sub_type: str) -> str:
    """Map a TC subType string to an RFLP layer letter (R/F/L/P) or '' if unknown."""
    return _RFLP_LAYER_MAP.get(sub_type, "")


@dataclass
class PlmxmlGeneralRelation:
    """Teamcenter GeneralRelation — carries RFLP trace links (Seg0Realize / Seg0Allocate / Seg0Satisfy / FND_TraceLink)."""
    id: str
    sub_type: str = ""
    related_refs: List[str] = field(default_factory=list)
    tc_label: str = ""
    properties: Dict[str, str] = field(default_factory=dict)


@dataclass
class PlmxmlForm:
    """Teamcenter Form — carries ItemRevision Master attributes and free-form TC properties."""
    id: str
    name: str = ""
    sub_type: str = ""
    sub_class: str = ""
    description: str = ""
    attributes: Dict[str, str] = field(default_factory=dict)
    properties: Dict[str, str] = field(default_factory=dict)


@dataclass
class PlmxmlRelationship:
    id: str
    source_id: str
    target_id: str
    relationship_type: str
    properties: Dict[str, str] = field(default_factory=dict)


@dataclass
class PlmxmlDocument:
    file_path: Path | None = None
    schema_version: str = ""
    author: str = ""
    date: str = ""
    root_refs: List[str] = field(default_factory=list)
    parts: Dict[str, PlmxmlPart] = field(default_factory=dict)
    product_views: Dict[str, PlmxmlProductView] = field(default_factory=dict)
    product_instances: List[PlmxmlProductInstance] = field(default_factory=list)
    processes: Dict[str, PlmxmlProcess] = field(default_factory=dict)
    process_views: Dict[str, PlmxmlProcessView] = field(default_factory=dict)
    process_instances: List[PlmxmlProcessInstance] = field(default_factory=list)
    change_notices: Dict[str, PlmxmlChangeNotice] = field(default_factory=dict)
    revisions: Dict[str, PlmxmlRevision] = field(default_factory=dict)
    transforms: Dict[str, PlmxmlTransform] = field(default_factory=dict)
    user_data: Dict[str, PlmxmlUserData] = field(default_factory=dict)
    documents: Dict[str, PlmxmlDocumentItem] = field(default_factory=dict)
    external_files: Dict[str, PlmxmlExternalFile] = field(default_factory=dict)
    requirements: Dict[str, PlmxmlRequirement] = field(default_factory=dict)
    general_relations: List[PlmxmlGeneralRelation] = field(default_factory=list)
    forms: Dict[str, PlmxmlForm] = field(default_factory=dict)
    relationships: List[PlmxmlRelationship] = field(default_factory=list)


def _parse_refs(value: str) -> List[str]:
    return [token for token in value.replace(",", " ").split() if token]


def _attrs(element: ET.Element) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for key, value in element.attrib.items():
        out[_local_name(key)] = value
    return out


def _parse_quantity(attrs: Dict[str, str]) -> int:
    qty_raw = attrs.get("quantity", attrs.get("qty", "1"))
    try:
        return int(float(qty_raw))
    except ValueError:
        return 1


def _parse_time_required(attrs: Dict[str, str]) -> float | None:
    raw_value = attrs.get("timeRequired", attrs.get("plannedTime", ""))
    if not raw_value:
        return None
    try:
        return float(raw_value)
    except ValueError:
        return None


def parse_plmxml_file(file_path: Path) -> PlmxmlDocument:
    tree = ET.parse(file_path)
    root = tree.getroot()

    root_attrs = _attrs(root)
    doc = PlmxmlDocument(
        file_path=file_path,
        schema_version=root_attrs.get("schemaVersion", "") or root_attrs.get("version", ""),
        author=root_attrs.get("author", ""),
        date=root_attrs.get("date", ""),
    )

    for elem in root.iter():
        tag = _local_name(elem.tag)
        attrs = _attrs(elem)
        elem_id = attrs.get("id", "")

        if not elem_id:
            continue

        if tag in {"Part", "PartRevision", "PartMaster", "Product", "ProductRevision"}:
            doc.parts[elem_id] = PlmxmlPart(
                id=elem_id,
                name=attrs.get("name", ""),
                part_number=attrs.get("partNumber", attrs.get("number", attrs.get("itemId", ""))),
                revision=attrs.get("revision", attrs.get("revisionId", "")),
                description=attrs.get("description", ""),
                part_type=attrs.get("partType", attrs.get("subType", tag)),
                master_ref=attrs.get("masterRef", attrs.get("baseRef", attrs.get("productRef", ""))),
                user_data_refs=_parse_refs(attrs.get("userDataRefs", "")),
                properties=attrs,
            )
        elif tag in {"ProductView", "ProductRevisionView", "View"}:
            doc.product_views[elem_id] = PlmxmlProductView(
                id=elem_id,
                name=attrs.get("name", ""),
                view_type=attrs.get("viewType", tag),
                root_refs=_parse_refs(attrs.get("rootRefs", attrs.get("instanceRefs", ""))),
                product_ref=attrs.get("productRef", attrs.get("revisionRef", "")),
                structure_type=attrs.get("structureType", attrs.get("type", "")),
                properties=attrs,
            )
        elif tag in {"ProductInstance", "Occurrence", "ProductOccurrence"}:
            doc.product_instances.append(
                PlmxmlProductInstance(
                    id=elem_id,
                    name=attrs.get("name", ""),
                    part_ref=attrs.get("partRef", attrs.get("instancedRef", attrs.get("productRef", ""))),
                    transform_ref=attrs.get("transformRef", ""),
                    parent_ref=attrs.get("parentRef", ""),
                    quantity=_parse_quantity(attrs),
                    occurrence_refs=_parse_refs(attrs.get("occurrenceRefs", attrs.get("childRefs", ""))),
                    user_data_refs=_parse_refs(attrs.get("userDataRefs", "")),
                    application_refs=_parse_refs(attrs.get("applicationRefs", attrs.get("representationRefs", ""))),
                    properties=attrs,
                )
            )
        elif tag in {"Process", "ProcessRevision", "Operation", "OperationRevision"}:
            doc.processes[elem_id] = PlmxmlProcess(
                id=elem_id,
                name=attrs.get("name", ""),
                process_type=attrs.get("processType", attrs.get("operationType", tag)),
                description=attrs.get("description", ""),
                time_required=_parse_time_required(attrs),
                resources=_parse_refs(attrs.get("resources", attrs.get("resourceRefs", ""))),
                properties=attrs,
            )
        elif tag in {"ProcessView", "ProcessRevisionView"}:
            doc.process_views[elem_id] = PlmxmlProcessView(
                id=elem_id,
                name=attrs.get("name", ""),
                root_process_refs=_parse_refs(attrs.get("rootProcessRefs", attrs.get("processRefs", ""))),
                product_refs=_parse_refs(attrs.get("productRefs", attrs.get("partRefs", ""))),
                properties=attrs,
            )
        elif tag in {"ProcessInstance", "ProcessOccurrence"}:
            doc.process_instances.append(
                PlmxmlProcessInstance(
                    id=elem_id,
                    process_ref=attrs.get("processRef", attrs.get("instancedRef", "")),
                    predecessor_refs=_parse_refs(attrs.get("predecessorRefs", attrs.get("predecessorRef", ""))),
                    product_instance_refs=_parse_refs(attrs.get("productInstanceRefs", attrs.get("occurrenceRefs", ""))),
                    properties=attrs,
                )
            )
        elif tag in {"ChangeNotice", "ECO", "ECN"}:
            doc.change_notices[elem_id] = PlmxmlChangeNotice(
                id=elem_id,
                name=attrs.get("name", ""),
                change_type=attrs.get("changeType", tag),
                status=attrs.get("status", ""),
                description=attrs.get("description", ""),
                date=attrs.get("date", ""),
                author=attrs.get("author", ""),
                affected_items=_parse_refs(attrs.get("affectedItems", attrs.get("affectedRefs", ""))),
                properties=attrs,
            )
        elif tag in {"Revision"}:
            doc.revisions[elem_id] = PlmxmlRevision(
                id=elem_id,
                revision_id=attrs.get("revisionId", attrs.get("revision", "")),
                base_ref=attrs.get("baseRef", ""),
                revision_type=attrs.get("revisionType", attrs.get("type", "")),
                date=attrs.get("date", ""),
                description=attrs.get("description", ""),
                change_notice_refs=_parse_refs(attrs.get("changeNoticeRefs", attrs.get("changeRef", ""))),
                properties=attrs,
            )
        elif tag in {"Transform"}:
            matrix_vals: List[float] = []
            for token in attrs.get("matrix", "").replace(",", " ").split():
                try:
                    matrix_vals.append(float(token))
                except ValueError:
                    continue
            doc.transforms[elem_id] = PlmxmlTransform(id=elem_id, matrix=matrix_vals)
        elif tag in {"UserData"}:
            values: Dict[str, str] = {}
            for child in list(elem):
                child_tag = _local_name(child.tag)
                child_attrs = _attrs(child)
                if child_tag == "UserValue":
                    title = child_attrs.get("title", child_attrs.get("name", "value"))
                    value = child_attrs.get("value", (child.text or "").strip())
                    values[title] = value
            doc.user_data[elem_id] = PlmxmlUserData(
                id=elem_id,
                type=attrs.get("type", ""),
                title=attrs.get("title", ""),
                values=values,
            )
        elif tag in {"Document", "DocumentRevision", "DataSet"}:
            doc.documents[elem_id] = PlmxmlDocumentItem(
                id=elem_id,
                name=attrs.get("name", ""),
                document_type=attrs.get("documentType", attrs.get("datasetType", tag)),
                description=attrs.get("description", ""),
                revision=attrs.get("revision", attrs.get("revisionId", "")),
                external_file_refs=_parse_refs(attrs.get("externalFileRefs", attrs.get("fileRefs", attrs.get("memberRefs", "")))),
                user_data_refs=_parse_refs(attrs.get("userDataRefs", "")),
                properties=attrs,
            )
        elif tag in {"ExternalFile", "DigitalFile"}:
            doc.external_files[elem_id] = PlmxmlExternalFile(
                id=elem_id,
                name=attrs.get("name", attrs.get("originalFileName", "")),
                location=attrs.get("location", attrs.get("locationRef", attrs.get("path", ""))),
                format=attrs.get("format", attrs.get("fileFormat", "")),
                mime_type=attrs.get("mimeType", attrs.get("contentType", "")),
                properties=attrs,
            )
        elif tag in {"Relationship", "Rel"}:
            source_id = attrs.get("source", attrs.get("sourceRef", ""))
            target_id = attrs.get("target", attrs.get("targetRef", ""))
            rel_type = attrs.get("type", attrs.get("relationshipType", tag))
            if source_id and target_id:
                doc.relationships.append(
                    PlmxmlRelationship(
                        id=elem_id,
                        source_id=source_id,
                        target_id=target_id,
                        relationship_type=rel_type,
                        properties=attrs,
                    )
                )
        elif tag in {"Requirement"}:
            doc.requirements[elem_id] = PlmxmlRequirement(
                id=elem_id,
                name=attrs.get("name", ""),
                catalogue_id=attrs.get("catalogueId", attrs.get("id", "")),
                properties=attrs,
            )
        elif tag in {"RequirementRevision"}:
            # Merge into matching Requirement master, or create standalone entry
            master_ref = attrs.get("masterRef", "").lstrip("#")
            body_text = ""
            last_mod_date = ""
            object_string = ""
            dataset_ref = ""
            ud_refs: List[str] = []
            for child in list(elem):
                ctag = _local_name(child.tag)
                cattrs = _attrs(child)
                if ctag == "PlainText":
                    body_text = (child.text or "").strip()
                elif ctag == "UserData":
                    for gc in list(child):
                        if _local_name(gc.tag) == "UserValue":
                            title = _attrs(gc).get("title", "")
                            val = _attrs(gc).get("value", "")
                            if title == "last_mod_date":
                                last_mod_date = val
                            elif title == "object_string":
                                object_string = val
                elif ctag == "AssociatedDataSet":
                    dataset_ref = cattrs.get("dataSetRef", "").lstrip("#")
            if master_ref and master_ref in doc.requirements:
                req = doc.requirements[master_ref]
                req.revision = attrs.get("revision", "")
                req.revision_id = elem_id
                req.body_text = body_text
                req.last_mod_date = last_mod_date
                req.object_string = object_string
                req.dataset_ref = dataset_ref
            else:
                # RequirementRevision without a visible master — store as own entry
                doc.requirements[elem_id] = PlmxmlRequirement(
                    id=elem_id,
                    name=attrs.get("name", ""),
                    catalogue_id=attrs.get("catalogueId", ""),
                    revision=attrs.get("revision", ""),
                    revision_id=elem_id,
                    master_ref=master_ref,
                    body_text=body_text,
                    last_mod_date=last_mod_date,
                    object_string=object_string,
                    dataset_ref=dataset_ref,
                    properties=attrs,
                )
        elif tag in {"GeneralRelation", "TraceabilityRelation"}:
            tc_label = ""
            for child in list(elem):
                if _local_name(child.tag) == "ApplicationRef":
                    tc_label = _attrs(child).get("label", "")
            doc.general_relations.append(
                PlmxmlGeneralRelation(
                    id=elem_id,
                    sub_type=attrs.get("subType", tag),
                    related_refs=[r.lstrip("#") for r in _parse_refs(attrs.get("relatedRefs", ""))],
                    tc_label=tc_label,
                    properties=attrs,
                )
            )
        elif tag in {"Form"}:
            form_attrs: Dict[str, str] = {}
            description = ""
            for child in list(elem):
                ctag = _local_name(child.tag)
                if ctag == "Description":
                    description = (child.text or "").strip()
                elif ctag == "UserData":
                    for gc in list(child):
                        if _local_name(gc.tag) == "UserValue":
                            gc_attrs = _attrs(gc)
                            title = gc_attrs.get("title", "")
                            value = gc_attrs.get("value", "")
                            if title:
                                form_attrs[title] = value
            doc.forms[elem_id] = PlmxmlForm(
                id=elem_id,
                name=attrs.get("name", ""),
                sub_type=attrs.get("subType", ""),
                sub_class=attrs.get("subClass", ""),
                description=description,
                attributes=form_attrs,
                properties=attrs,
            )

    if "rootRefs" in root_attrs:
        doc.root_refs = _parse_refs(root_attrs.get("rootRefs", ""))

    return doc
