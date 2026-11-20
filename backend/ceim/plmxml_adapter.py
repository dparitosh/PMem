"""Teamcenter PLMXML adapter for the governed CEIM batch contract.

PLMXML is retained as the source standard.  The adapter does not claim that a
Teamcenter export is an AP242 exchange; an approved AP242 mapping remains a
separate semantic crosswalk after CEIM normalization.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any
from defusedxml import ElementTree as ET

from backend.Services.data_import_service import DataImportService

from .contract import CEIMContract, contract


def _source_record(record: dict[str, Any]) -> dict[str, Any]:
    attributes = dict(record.get("attributes") or {})
    for key in ("name", "part_number", "revision"):
        value = record.get(key)
        if value not in (None, ""):
            attributes[key] = value
    return {
        "source_type": str(record.get("type") or ""),
        "source_id": str(record.get("id") or ""),
        "attributes": attributes,
    }


def _reference_values(value: Any) -> list[str]:
    """Normalize PLMXML scalar/list reference attributes without guessing links."""
    if isinstance(value, (list, tuple, set)):
        values = value
    else:
        values = str(value or "").replace(",", " ").split()
    return [str(item).strip().removeprefix("#") for item in values if str(item).strip()]


def plmxml_to_ceim_batch(content: bytes, *, ceim: CEIMContract | None = None) -> dict[str, Any]:
    """Parse a bounded PLMXML export into a non-persisted CEIM batch.

    The file is written only to an operating-system temporary path because the
    mature parser operates on paths.  It is deleted before the function returns.
    """
    if not content:
        raise ValueError("PLMXML content is empty")
    active_contract = ceim or contract
    temporary_path = ""
    try:
        with tempfile.NamedTemporaryFile(prefix="depo-plmxml-", suffix=".xml", delete=False) as handle:
            temporary_path = handle.name  # set before writing so a failed write is still cleaned up
            handle.write(content)
        parsed = DataImportService._parse_plmxml(temporary_path)
    finally:
        if temporary_path:
            Path(temporary_path).unlink(missing_ok=True)

    if parsed.get("error"):
        raise ValueError(f"PLMXML parsing failed: {parsed['error']}")
    raw_entities = list(parsed.get("entities") or [])
    known: set[str] = set()
    for record in raw_entities:
        identifier = str(record.get("id") or "").strip()
        if not identifier:
            continue
        if identifier in known:
            raise ValueError(f"PLMXML document contains duplicate id: {identifier}")
        known.add(identifier)
    # Preserve declared Teamcenter requirement-specification types and trace
    # carriers. Never infer a requirement or a directed pair from its label.
    xml_root = ET.fromstring(content)
    source_elements = {e.get('id'): e for e in xml_root.iter() if e.get('id')}
    for record in raw_entities:
        element = source_elements.get(str(record.get('id') or ''))
        if element is None:
            continue
        tag = element.tag.rsplit('}', 1)[-1]
        subtype = ''.join(c.lower() for c in element.get('subType', '') if c.isalnum())
        specification = (tag == 'Product' and subtype == 'requirementspec') or (tag == 'ProductRevision' and subtype == 'requirementspecrevision')
        if specification:
            record['type'] = 'RequirementSpecificationRevision' if tag == 'ProductRevision' else 'RequirementSpecification'
            attributes = record.setdefault('attributes', {})
            attributes.update({'subType': element.get('subType'), 'revision': element.get('revision'),
                               'master_ref': element.get('masterRef', '')})
    by_source_id = {record['id']: record for record in raw_entities}
    for identifier, element in source_elements.items():
        tag = element.tag.rsplit('}', 1)[-1]
        source_type = 'SourceOccurrence' if tag == 'Occurrence' else tag
        if source_type not in {'SourceOccurrence','ProcessRevision','ProcessRevisionView','ProcessInstance','ProcessOccurrence','WorkArea','WorkAreaRevision','WorkAreaInstance','WorkAreaOccurrence','PlantRevisionView'}:
            # Product revision views point to their exact revision, not a guessed master.
            if tag == 'ProductRevisionView' and identifier in by_source_id:
                by_source_id[identifier].setdefault('attributes', {})['product_ref'] = element.get('revisionRef', '')
            continue
        record = by_source_id.get(identifier)
        if record is None:
            record = {'id':identifier,'name':element.get('name'),'attributes':{}}
            raw_entities.append(record);by_source_id[identifier]=record;known.add(identifier)
        record['type'] = source_type
        attributes = record.setdefault('attributes', {})
        attributes.update(dict(element.attrib))
        for xml_key, key in [('masterRef','master_ref'),('revisionRef','revision_ref'),('partRef','part_ref'),('instancedRef','instanced_ref'),('parentRef','parent_ref'),('occurrenceRefs','occurrence_refs'),('instanceRefs','instance_refs')]:
            if element.get(xml_key):attributes[key]=element.get(xml_key)
    # Retain explicitly mapped extension resources without classifying them as Parts.
    for element in xml_root.iter():
        source_type = element.tag.removeprefix("{http://www.plmxml.org/Schemas/PLMXMLSchema}")
        identifier = element.get('id')
        is_trace = source_type == 'GeneralRelation' and element.get('subType') == 'FND_TraceLink'
        if identifier and identifier not in known and (source_type in {'Terminal', 'ConnectionRevision', 'GDE'} or is_trace):
            attributes = dict(element.attrib)
            if is_trace:
                attributes['related_refs'] = element.get('relatedRefs', '')
                names = [e.get('value') for e in element.iter() if e.tag.rsplit('}', 1)[-1] == 'UserValue' and e.get('title') == 'name' and e.get('value')]
                attributes['name'] = names[0] if names else 'Recorded trace link'
            raw_entities.append({'id':identifier,'type':'TraceLink' if is_trace else source_type,
                                 'name':attributes.get('name'), 'attributes':attributes})
            known.add(identifier)
    normalized_entities = [
        active_contract.normalize_entity(standard="plmxml", record=_source_record(record))
        for record in raw_entities
        if str(record.get("type") or "") in active_contract.mapping_pack("plmxml")["entities"]
    ]
    emitted_ids = {str(entity["id"]).split(":", 1)[-1] for entity in normalized_entities}
    resource_ids = {record["id"] for record in raw_entities if record["type"] in {"Terminal", "ConnectionRevision", "GDE"}}
    relationship_records: list[dict[str, Any]] = []
    relationship_keys: set[tuple[str, str, str]] = set()
    unresolved_references: set[tuple[str, str, str]] = set()

    def add_relationship(*, source: str, target: str, source_type: str, source_key: str) -> None:
        if not source or not target or source not in emitted_ids or target not in emitted_ids:
            unresolved_references.add((source, target, source_key))
            return
        # A ProductInstance can reference a mapped extension Resource instead
        # of a Part; preserve the relationship but never misclassify it.
        if source_type == "instance_part" and target in resource_ids:
            source_type = "instance_resource"
        key = (source, target, source_type)
        if key in relationship_keys:
            return
        relationship_keys.add(key)
        relationship_records.append(active_contract.normalize_relationship(
            standard="plmxml",
            record={"source_type": source_type, "source_id": source,
                    "target_id": target, "source_key": source_key},
        ))

    # Mapping-pack rules are the authoritative structural contract. They name
    # the XML/parser field that creates each edge, so attributes such as name
    # or revision cannot accidentally become relationships.
    for record in raw_entities:
        attributes = dict(record.get("attributes") or {})
        for rule in active_contract.mapping_pack("plmxml").get("reference_rules", []):
            if rule.get("source_type") != record.get("type"):
                continue
            source = str(record.get("id") or "")
            for target in _reference_values(attributes.get(str(rule.get("attribute") or ""))):
                if rule.get("reverse"):
                    source, target = target, source
                add_relationship(
                    source=source, target=target,
                    source_type=str(rule["relationship_source_type"]),
                    source_key=str(rule["attribute"]),
                )
                if rule.get("reverse"):
                    source, target = target, source

    # Keep parser-extracted edges only as a compatibility fallback for source
    # variants that do not expose a declared mapping field.
    for relationship in list(parsed.get("relationships") or []):
        # Same-document PLMXML references are URI fragments, while parser
        # entity identifiers are bare XML ids. Do not rewrite external URIs.
        source = str(relationship.get("source") or "").removeprefix("#")
        target = str(relationship.get("target") or "").removeprefix("#")
        relation_type = str(relationship.get("type") or "")
        if not source or not target:
            continue
        if relation_type == "HAS_INSTANCE":
            # PLMXML parser reports Part -> occurrence.  CEIM's HAS_PART is
            # modeled from the occurrence/assembly to its referenced Part.
            source, target, source_type = target, source, "instance_part"
            if target in resource_ids:
                source_type = "instance_resource"
        elif relation_type == "CONTAINS":
            source_type = "assembly_child"
        else:
            continue
        add_relationship(source=source, target=target, source_type=source_type, source_key=f"parser:{relation_type}")
    return {
        "standard": "plmxml",
        "entities": normalized_entities,
        "relationships": relationship_records,
        "mapping_diagnostics": {
            "status":"review_required" if unresolved_references else "complete_for_declared_profile",
            "unresolved_reference_samples":[{"source_id":source,"target_id":target,"source_key":key}
                for source,target,key in sorted(unresolved_references)[:50]],
            "unresolved_reference_samples_complete":len(unresolved_references)<=50,
        },
        "source_summary": {
            "parsed_relationships": len(parsed.get("relationships") or []),
            "emitted_relationships": len(relationship_records),
            "declared_reference_rules": len(active_contract.mapping_pack("plmxml").get("reference_rules", [])),
            "emitted_structural_relationships": len(relationship_records),
            "unmapped_relationships": max(0, len(parsed.get("relationships") or []) - len(relationship_records)),
            "unresolved_references": len(unresolved_references),
            "schema_version": parsed.get("schema_version"),
            "parts": int(parsed.get("total_parts") or 0),
            "product_instances": int(parsed.get("total_instances") or 0),
            "processes": int(parsed.get("total_processes") or 0),
            "requirements": int(parsed.get("total_requirements") or 0),
            "change_notices": int(parsed.get("total_changes") or 0),
        },
    }
