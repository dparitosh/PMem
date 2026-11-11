"""Read named SysML views from immutable retained XMI, without changing the model."""
from functools import lru_cache
from pathlib import Path
from lxml import etree
from backend.Services.xmi_parser import XMIParser
from backend.Services.xmi_validation import validate_xmi_root


class ModelContextUnavailable(RuntimeError):
    pass


def _context_query(query, params):
    from backend.core.graph import query_with_timeout
    try:
        return query_with_timeout(query, params, timeout=10) or []
    except Exception as exc:
        import logging
        logging.getLogger(__name__).exception('Model engineering-context graph read failed')
        raise ModelContextUnavailable('Engineering associations are temporarily unavailable; the source diagram remains usable') from exc


def local(value):
    return value.rsplit('}', 1)[-1]


def read_diagrams(path):
    path = Path(path)
    if path.stat().st_size > 25_000_000:
        raise ValueError('XMI diagram source exceeds the 25 MB interactive viewer limit')
    try:
        root = etree.parse(str(path), etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False))
    except etree.XMLSyntaxError as exc:
        raise ValueError('Retained XMI is not well-formed XML; re-import a valid source') from exc
    if root.docinfo.doctype:
        raise ValueError('XMI DTD declarations are not supported')
    validate_xmi_root(root.getroot())
    parser = XMIParser()
    parsed = parser.parse(path)
    index = {parser._attr(e, 'id'): e for e in root.getroot().iter() if parser._attr(e, 'id')}
    nodes = {}
    for item in parsed['nodes']:
        props = item['properties']
        identity = props.get('id')
        if identity:
            nodes[identity] = {'id': identity, 'label': props.get('name') or item.get('label') or identity,
                               'type': props.get('appliedStereotype') or props.get('stereotype') or props.get('type') or item.get('label'), 'properties': props}
    # Preserve profile applications and owned features even for vendor SysML namespaces.
    for element in root.getroot().iter():
        bases = [v for k,v in element.attrib.items() if local(k).startswith('base_')]
        for identity in bases:
            if identity in nodes:
                stereotype = local(element.tag)
                props = nodes[identity]['properties']
                props.setdefault('profile_applications', []).append({'stereotype':stereotype, **{local(k):v for k,v in element.attrib.items() if not local(k).startswith('base_')}})
                if any(token in stereotype.lower() for token in ('requirement','block','constraint','valueproperty','constraintparameter','port')):
                    nodes[identity]['type'] = stereotype
                # Keep the primary profile stable; all applications remain namespaced above.
                for key, value in element.attrib.items():
                    if not local(key).startswith('base_'):
                        props.setdefault('profile_' + local(key), value)
    for identity,node in nodes.items():
        element=index.get(identity)
        if element is None:
            continue
        features=[]
        for child in element:
            if local(child.tag) in {'ownedAttribute','ownedPort','ownedOperation','ownedRule'}:
                features.append(' '.join(f'{local(k)}={v}' for k,v in child.attrib.items() if local(k) not in {'id'}))
        if features:
            node['properties']['ownedFeatures'] = features
    diagrams = []
    for element in root.getroot().iter():
        if local(element.tag) != 'ownedDiagram':
            continue
        representation = next((e for e in element.iter() if local(e.tag) == 'DiagramRepresentationObject'), None)
        members = list(dict.fromkeys(e.get('href', '').lstrip('#') for e in element.iter() if local(e.tag) == 'usedObjects' and e.get('href', '').startswith('#')))
        if len(members) > 4096 or len(diagrams) >= 256:
            raise ValueError('XMI diagram exceeds the interactive view limit')
        for identity in members:
            if identity in nodes or identity not in index:
                continue
            e = index[identity]
            kind = parser._xmi_type(e) or local(e.tag)
            props = {local(k): v for k, v in e.attrib.items()}
            nodes[identity] = {'id': identity, 'label': e.get('name') or kind, 'type': kind, 'properties': props}
        diagrams.append({'id': parser._attr(element, 'id'), 'name': element.get('name') or 'Unnamed diagram',
                         'type': representation.get('type', 'Unknown') if representation is not None else 'Unknown',
                         'nodeIds': [identity for identity in members if identity in nodes and
                            not any(token in str(nodes[identity]['type']).split(':')[-1] for token in ('Association','Abstraction','Dependency','Include','Extend','ConnectorEnd','Connector','Generalization')) and
                            not (representation is not None and ('Block Definition' in representation.get('type','') or 'Use Case' in representation.get('type','')) and str(nodes[identity]['type']).endswith(('Property','Port')))],
                         'unresolvedIds': [identity for identity in members if identity not in nodes],
                         'layout': 'generated', 'external_layout': any(local(e.tag) == 'binaryObject' for e in element.iter())})
    if not diagrams:
        raise ValueError('The retained XMI contains no named diagram definitions')
    links = []
    for i, relation in enumerate(parsed['relationships']):
        source = relation.get('from_props', {}).get('id'); target = relation.get('to_props', {}).get('id')
        if source in nodes and target in nodes:
            links.append({'id': f'xmi-relation:{i}', 'source': source, 'target': target, 'type': relation['type'], 'properties': relation.get('properties', {})})
    # Include/extend and binding connectors are source relations, not box-shaped elements.
    for identity,element in index.items():
        kind=parser._xmi_type(element).split(':')[-1]
        source=target=None
        if kind in {'Include','Extend'}:
            parent=element.getparent()
            source=parser._attr(parent,'id') if parent is not None else None
            target=element.get('addition') or element.get('extendedCase')
        elif kind=='Connector':
            ends=[e.get('role') for e in element if local(e.tag)=='end' and e.get('role')]
            if len(ends)==2:
                source,target=ends
        if source in nodes and target in nodes:
            links.append({'id':identity,'source':source,'target':target,'type':kind.upper(),'properties':{'source_xmi_id':identity}})
    if len(nodes) > 10000:
        raise ValueError('XMI model exceeds the interactive element limit')
    return {'nodes': list(nodes.values()), 'links': links, 'representations': diagrams,
            'message': 'Named views and model semantics read from retained XMI. Layout is generated; external MagicDraw drawing streams are not available. Only relationships with endpoints in the selected view are shown.'}


@lru_cache(maxsize=8)
def _retained(source_id):
    from backend.artifact_store import artifact_store
    try:
        path = artifact_store.resolve(source_id)[1]
    except ValueError as exc:
        if str(exc) == 'artifact_id was not found':
            raise LookupError('Retained XMI source is missing; restore or re-import it') from exc
        raise ValueError('Retained XMI integrity could not be verified; restore or re-import it') from exc
    return read_diagrams(path)


def retained_diagrams(ontology_id):
    from backend.ontology_service.catalog import catalog
    metadata = catalog.get(ontology_id)
    if not metadata:
        raise LookupError('Model source is not registered')
    if not str(metadata.get('source_filename', '')).lower().endswith(('.xmi', '.mdxml')):
        raise ValueError('This ontology has no retained XMI source')
    source_id = (metadata.get('engineering_artifacts') or {}).get('source')
    if not source_id:
        raise LookupError('Original XMI artifact is unavailable; retain the original model through Import')
    return {**_retained(source_id), 'ontology_id': ontology_id, 'source_artifact_id': source_id}


def model_context(ontology_id, source_id):
    """Resolve one original XMI identity and its recorded graph neighbors, never by name."""
    manifest = retained_diagrams(ontology_id)
    if not any(node['id'] == source_id for node in manifest['nodes']):
        raise LookupError('Element is not present in this retained model')
    rows = _context_query('''
        MATCH (n)
        WHERE n.ontology_id = $ontology_id
          AND (properties(n)['source_xmi_id'] = $source_id OR n.iri ENDS WITH $suffix)
        RETURN elementId(n) AS id, properties(n) AS properties
        LIMIT 2
    ''', {'ontology_id': ontology_id, 'source_id': source_id, 'suffix': '/' + source_id})
    if len(rows) != 1:
        return {'status': 'ambiguous' if rows else 'unpublished', 'source_id': source_id,
                'nodes': [], 'links': [], 'message': 'No unique published graph identity is available for this model element.'}
    identity = rows[0]['id']
    neighbors = _context_query('''
        MATCH (n)-[r]-(other) WHERE elementId(n) = $identity
        RETURN elementId(other) AS id, properties(other) AS properties,
               labels(other) AS labels, elementId(r) AS relationship_id,
               coalesce(r.predicate, type(r)) AS relationship,
               elementId(startNode(r)) AS source, elementId(endNode(r)) AS target
        ORDER BY relationship_id LIMIT 101
    ''', {'identity': identity})
    return {'status': 'resolved', 'source_id': source_id, 'node_id': identity,
            'properties': rows[0]['properties'], 'truncated': len(neighbors) > 100,
            'nodes': [{'id': row['id'], 'properties': row['properties'], 'labels': row['labels']} for row in neighbors[:100]],
            'links': [{'id': row['relationship_id'], 'type': row['relationship'], 'source': row['source'], 'target': row['target']} for row in neighbors[:100]]}
