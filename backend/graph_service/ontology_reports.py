"""Full ontology-scoped OSLC coverage; never infer business outcomes from schemas."""


def ontology_report(ontology_id: str) -> dict:
    from backend.Services.oslc_service import OSLCService
    from backend.Services.graph_view_service import GraphViewService

    scope = OSLCService._ontology_domain_scope('ontology:' + ontology_id)
    if not scope:
        raise ValueError('Select a registered ontology')
    types = ['requirements', 'requirement-collections', 'architecture-resources',
             'change-requests', 'test-cases', 'test-results']
    predicates = [OSLCService._resource_type_predicate(kind) for kind in types]
    columns = ', '.join(f'sum(CASE WHEN {predicate} THEN 1 ELSE 0 END) AS c{i}'
                        for i, predicate in enumerate(predicates))
    scoped = "(toString(coalesce(n.ontology_id, '')) = $ontology_id OR ($ontology_prefix <> '' AND toString(coalesce(n.ontology_prefix, n.prefix, '')) = $ontology_prefix))"
    query = f"""
    CALL {{ MATCH (n) WHERE {scoped} AND NOT n:GraphChunk AND NOT n:DatasheetChunk
      RETURN count(n) AS resources, {columns},
      sum(CASE WHEN {' OR '.join(predicates)} THEN 0 ELSE 1 END) AS unmapped }}
    CALL {{ MATCH (n)-[r]->(target) WHERE {scoped}
      AND NOT n:GraphChunk AND NOT n:DatasheetChunk
      AND NOT target:GraphChunk AND NOT target:DatasheetChunk
      RETURN count(r) AS outgoing_links }}
    RETURN resources, unmapped, outgoing_links, {', '.join(f'c{i}' for i in range(len(types)))}
    """
    rows = GraphViewService._run(query, {'ontology_id': scope['ontology_id'], 'ontology_prefix': scope['prefix']})
    if not rows:
        raise RuntimeError('Ontology report aggregation returned no result')
    row = rows[0]
    domains = ['RM', 'RM', 'AM', 'CM', 'QM', 'QM']
    return {'ontology_id': scope['ontology_id'], 'prefix': scope['prefix'],
            'resources': row['resources'], 'unmapped': row['unmapped'],
            'outgoing_links': row['outgoing_links'], 'sampled': False,
            'categories': [{'resource_type': kind, 'domain': domains[i], 'count': row[f'c{i}']}
                           for i, kind in enumerate(types)],
            'notes': ['Domain counts use the same retained metadata predicates as OSLC queries; categories may overlap.',
                      'Unmapped records are not necessarily invalid. Ontology declarations do not establish test outcomes.',
                      'Outgoing links include links to other ontologies. QIF, AP242 and ReqIF are selected through the loaded ontology registry.']}
