"""Non-publishing SysML v1 XMI and SysML v2 JSON model import."""
import json
from typing import Any
from defusedxml import ElementTree as ET
from .contract import contract
from backend.Services.xmi_validation import validate_xmi_root, xmi_attribute, local_reference


def mbse_to_ceim_batch(content: bytes, *, version: str) -> dict[str, Any]:
    standard = 'sysml-v' + version
    records, links = [], []
    relation_kinds = {'Satisfy': 'SATISFIES', 'SatisfyRequirementUsage': 'SATISFIES', 'Verify': 'VERIFY', 'RequirementVerificationMembership': 'VERIFY', 'DeriveReqt': 'DERIVED_FROM'}
    if version == '1':
        if b'<!DOCTYPE' in content.replace(b'\x00', b'').upper() or b'<!ENTITY' in content.replace(b'\x00', b'').upper():
            raise ValueError('XMI DTD and entity declarations are not supported')
        try:
            root = ET.fromstring(content)
        except ET.ParseError as exc:
            raise ValueError('XMI XML is invalid') from exc
        validate_xmi_root(root)
        def attr(e, name):
            return xmi_attribute(e, name)
        def refs(e, name):
            values = list(e.get(name, '').split())
            for child in e:
                if str(child.tag).rsplit('}', 1)[-1] == name:
                    values.extend((attr(child, 'idref') or child.get('href', '')).split())
            return [local_reference(value) for value in values]
        for e in root.iter():
            identifier = attr(e, 'id')
            if not identifier:
                continue
            kind = attr(e, 'type').split(':')[-1] or e.tag.rsplit('}', 1)[-1]
            raw = dict(e.attrib)
            raw['client_refs'], raw['supplier_refs'] = refs(e, 'client'), refs(e, 'supplier')
            raw['source_children_xml'] = [ET.tostring(child, encoding='unicode') for child in e
                                          if str(child.tag).rsplit('}', 1)[-1] in {'ownedComment', 'lowerValue', 'upperValue'}]
            records.append({'id': identifier, 'name': e.get('name', identifier), 'kind': kind, 'raw': raw})
            for child in e:
                child_id = attr(child, 'id')
                if child_id:
                    links.append((identifier, child_id, 'CONTAINS'))
            for source in raw['client_refs']:
                for target in raw['supplier_refs']:
                    links.append((source, target, 'TRACE'))
        # Profile applications refer to the underlying UML element.
        by_id = {r['id']: r for r in records}
        for e in root.iter():
            for key, value in e.attrib.items():
                if key.rsplit('}', 1)[-1].startswith('base_'):
                    value = local_reference(value)
                    if value not in by_id:
                        raise ValueError('SysML stereotype references an unknown model element')
                    by_id[value]['kind'] = e.tag.rsplit('}', 1)[-1]
                    by_id[value]['raw']['stereotype_attributes'] = dict(e.attrib)
                    if by_id[value]['kind'] in relation_kinds:
                        raw = by_id[value]['raw']
                        for source in raw.get('client_refs', []):
                            for target in raw.get('supplier_refs', []):
                                if (source, target, 'TRACE') in links:
                                    links.remove((source, target, 'TRACE'))
                                links.append((source, target, relation_kinds[by_id[value]['kind']]))
    elif version == '2':
        data = json.loads(content)
        if not isinstance(data, (list, dict)):
            raise ValueError('SysML v2 document must be an array or an object containing elements')
        elements = data if isinstance(data, list) else data.get('elements')
        if not isinstance(elements, list):
            raise ValueError('SysML v2 requires an element array or an object containing elements')
        for e in elements:
            if not isinstance(e, dict):
                raise ValueError('SysML v2 elements must be objects')
            identifier = e.get('@id') or e.get('elementId')
            if not isinstance(identifier, str) or not identifier.strip():
                raise ValueError('SysML v2 element requires a non-empty string @id/elementId')
            identifier = identifier.strip()
            kind = e.get('@type', 'Element')
            if isinstance(kind, list) and len(kind) == 1:
                kind = kind[0]
            if not isinstance(kind, str) or not kind.strip():
                raise ValueError('SysML v2 @type requires one non-empty type name')
            kind = kind.strip()
            records.append({'id': identifier, 'name': e.get('declaredName') or e.get('name') or identifier, 'kind': kind, 'raw': e})
            def refs(value):
                result = []
                for item in (value if isinstance(value, list) else [value]):
                    if item is None:
                        continue
                    ref = (item.get('@id') or item.get('elementId')) if isinstance(item, dict) else item
                    if not isinstance(ref, str) or not ref.strip():
                        raise ValueError('SysML v2 references require non-empty string IDs')
                    result.append(ref.strip())
                return result
            for owner in refs(e.get('owner')):
                links.append((owner, identifier, 'CONTAINS'))
            for source in refs(e.get('source')):
                for target in refs(e.get('target')):
                    links.append((source, target, relation_kinds.get(kind, 'TRACE')))
    else:
        raise ValueError('Unsupported SysML version')
    if not records:
        raise ValueError('No model elements found')
    ids = [r['id'] for r in records]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate model identifiers')
    id_set = set(ids)
    unresolved = [link for link in links if link[0] not in id_set or link[1] not in id_set]
    if unresolved:
        raise ValueError(f'Model has {len(unresolved)} unresolved references; include referenced elements')
    requirement_kinds = {'Requirement', 'RequirementDefinition', 'RequirementUsage'}
    entities = [contract.normalize_entity(standard=standard, record={'source_id': r['id'], 'source_type': 'Requirement' if r['kind'].rsplit(':', 1)[-1] in requirement_kinds else 'Element', 'attributes': {'name': r['name'], 'model_type': r['kind'], 'source_payload': json.dumps(r['raw'], sort_keys=True)}}) for r in records]
    relationships = [contract.normalize_relationship(standard=standard, record={'source_type': 'VERIFIED_BY' if kind == 'VERIFY' else kind, 'source_id': target if kind == 'VERIFY' else source, 'target_id': source if kind == 'VERIFY' else target}) for source, target, kind in dict.fromkeys(links)]
    return {'standard': standard, 'entities': entities, 'relationships': relationships, 'source_summary': {'elements': len(entities), 'relationships': len(relationships)}, 'ceim_version': contract.version}
