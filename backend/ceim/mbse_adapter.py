"""Non-publishing SysML v1 XMI and SysML v2 JSON model import."""
import json
from typing import Any
from defusedxml import ElementTree as ET
from .contract import contract


def mbse_to_ceim_batch(content: bytes, *, version: str) -> dict[str, Any]:
    standard = 'sysml-v' + version
    records, links = [], []
    relation_kinds = {'Satisfy': 'SATISFIES', 'SatisfyRequirementUsage': 'SATISFIES', 'Verify': 'VERIFY', 'RequirementVerificationMembership': 'VERIFY', 'DeriveReqt': 'DERIVED_FROM'}
    if version == '1':
        root = ET.fromstring(content)
        def attr(e, name):
            return next((v for k, v in e.attrib.items() if k.rsplit('}', 1)[-1] == name), '')
        for e in root.iter():
            identifier = attr(e, 'id')
            if not identifier:
                continue
            kind = attr(e, 'type').split(':')[-1] or e.tag.rsplit('}', 1)[-1]
            records.append({'id': identifier, 'name': e.get('name', identifier), 'kind': kind, 'raw': dict(e.attrib)})
            for child in e:
                child_id = attr(child, 'id')
                if child_id:
                    links.append((identifier, child_id, 'CONTAINS'))
            for source in e.get('client', '').split():
                for target in e.get('supplier', '').split():
                    links.append((source, target, 'TRACE'))
        # Profile applications refer to the underlying UML element.
        by_id = {r['id']: r for r in records}
        for e in root.iter():
            for key, value in e.attrib.items():
                if key.startswith('base_') and value in by_id:
                    by_id[value]['kind'] = e.tag.rsplit('}', 1)[-1]
                    by_id[value]['raw'].update(e.attrib)
                    if by_id[value]['kind'] in relation_kinds:
                        raw = by_id[value]['raw']
                        for source in raw.get('client', '').split():
                            for target in raw.get('supplier', '').split():
                                if (source, target, 'TRACE') in links:
                                    links.remove((source, target, 'TRACE'))
                                links.append((source, target, relation_kinds[by_id[value]['kind']]))
    elif version == '2':
        data = json.loads(content)
        elements = data if isinstance(data, list) else data.get('elements')
        if not isinstance(elements, list):
            raise ValueError('SysML v2 requires an element array or an object containing elements')
        for e in elements:
            if not isinstance(e, dict):
                raise ValueError('SysML v2 elements must be objects')
            identifier = e.get('@id') or e.get('elementId')
            if not identifier:
                raise ValueError('SysML v2 element is missing @id/elementId')
            records.append({'id': identifier, 'name': e.get('declaredName') or e.get('name') or identifier, 'kind': e.get('@type', 'Element'), 'raw': e})
            def refs(value):
                return [v.get('@id') if isinstance(v, dict) else v for v in (value if isinstance(value, list) else [value]) if v]
            for owner in refs(e.get('owner')):
                links.append((owner, identifier, 'CONTAINS'))
            for source in refs(e.get('source')):
                for target in refs(e.get('target')):
                    links.append((source, target, relation_kinds.get(e.get('@type'), 'TRACE')))
    else:
        raise ValueError('Unsupported SysML version')
    if not records:
        raise ValueError('No model elements found')
    ids = [r['id'] for r in records]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate model identifiers')
    unresolved = [link for link in links if link[0] not in ids or link[1] not in ids]
    if unresolved:
        raise ValueError(f'Model has {len(unresolved)} unresolved references; include referenced elements')
    entities = [contract.normalize_entity(standard=standard, record={'source_id': r['id'], 'source_type': 'Requirement' if 'Requirement' in r['kind'] else 'Element', 'attributes': {'name': r['name'], 'model_type': r['kind'], 'source_payload': json.dumps(r['raw'], sort_keys=True)}}) for r in records]
    relationships = [contract.normalize_relationship(standard=standard, record={'source_type': 'VERIFIED_BY' if kind == 'VERIFY' else kind, 'source_id': target if kind == 'VERIFY' else source, 'target_id': source if kind == 'VERIFY' else target}) for source, target, kind in dict.fromkeys(links)]
    return {'standard': standard, 'entities': entities, 'relationships': relationships, 'source_summary': {'elements': len(entities), 'relationships': len(relationships)}, 'ceim_version': contract.version}
