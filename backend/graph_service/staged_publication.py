"""Committed preparation and bounded activation with durable reader exclusion."""
import json
import hashlib
import logging
import time
from datetime import datetime, timezone


def publish_initial(session, *, ontology_id, publication_id, prefix, resources,
                    relationships, relation_queries, resource_query, timeout, unit_of_work,
                    activation_timeout=None, query_factory=None, artifact_sha256=None):
    if not publication_id:
        return None
    deadline = time.monotonic() + timeout

    def read(statement, **params):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('Publication staging deadline reached; checkpoints are retained')
        return session.run(query_factory(statement, timeout=min(10, remaining)) if query_factory else statement, **params)

    def transaction(operation):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('Publication write deadline reached; committed checkpoints are retained')
        return unit_of_work(timeout=min(30, remaining))(operation)

    # Activation updates stable identities for both first and later revisions;
    # no preliminary graph-wide resource count is needed.
    resource_merge = 'MERGE (node:OntologyResource {ontology_id: $ontology_id, iri: row.iri})'
    if resource_query.count(resource_merge) != 1:
        raise ValueError('Resource query is incompatible with isolated staging')
    batch_size = 1000
    total_relationships = sum(len(rows) for rows in relationships.values())
    # Preserve the manifest encoding without allocating a second full graph-sized
    # JSON string and byte buffer during large publications.
    manifest = hashlib.sha256()
    for fragment in json.JSONEncoder(sort_keys=True).iterencode([prefix, resources, relationships]):
        if time.monotonic() >= deadline:
            raise TimeoutError('Publication manifest preparation exceeded its deadline')
        manifest.update(fragment.encode('utf-8'))
    manifest_sha256 = manifest.hexdigest()
    params = dict(ontology_id=ontology_id, publication_id=publication_id)
    receipt = read('MATCH (p:OntologyPublication {ontology_id:$ontology_id, publication_id:$publication_id}) '
        'RETURN p {.*} AS receipt', **params).single()
    receipt = dict(receipt['receipt']) if receipt else {}
    # Older atomic publishers wrote completed receipts without staging metadata.
    # A caller-supplied identifier and matching counts do not prove equal content.
    # Legacy receipts are reusable only when their identity is the verified hash
    # of the bytes received by the publisher.
    legacy_completed = (receipt.get('status') == 'published'
                        and receipt.get('current') is True
                        and 'manifest_sha256' not in receipt
                        and artifact_sha256 is not None
                        and publication_id == artifact_sha256
                        and receipt.get('prefix') == prefix
                        and receipt.get('resources') == len(resources)
                        and receipt.get('relationships') == total_relationships
                        and receipt.get('hierarchy_edges') == len(relationships['SUBCLASS_OF']) + len(relationships['HAS_PART']))
    if receipt and not legacy_completed and (receipt.get('manifest_sha256') != manifest_sha256
                    or receipt.get('resources_expected') != len(resources)
                    or receipt.get('relationships_expected') != total_relationships
                    or receipt.get('batch_size') != batch_size):
        raise ValueError('Staged publication manifest changed; retain it for reconciliation')
    if receipt.get('status') == 'published':
        if not receipt.get('current'):
            raise ValueError('Publication was superseded; use a new publication identity')
        from backend.depo_platform.graph_access import reconcile_activation
        reconcile_activation(ontology_id, publication_id, {**receipt, **params})
        from .publication_cleanup import try_cleanup_completed_staging
        try_cleanup_completed_staging(session, **params, query_factory=query_factory)
        return {'status': 'success', **params, 'resources': len(resources),
                'relationships': total_relationships,
                'hierarchy_edges': receipt['hierarchy_edges']}

    @transaction
    def initialize(tx):
        tx.run('MERGE (p:OntologyPublication {ontology_id:$ontology_id, publication_id:$publication_id}) '
               "ON CREATE SET p.status='staging', p.current=false, p.resource_offset=0, "
               "p.relationship_offsets='{}', p.resources_expected=$resources, "
               'p.relationships_expected=$relationships, p.batch_size=$batch_size, p.manifest_sha256=$manifest_sha256',
               **params, resources=len(resources), relationships=total_relationships,
               batch_size=batch_size, manifest_sha256=manifest_sha256).consume()
    session.execute_write(initialize)
    staged_query = resource_query.replace(
        resource_merge,
        'MERGE (node:StagedOntologyResource {ontology_id: $ontology_id, publication_id: $publication_id, iri: row.iri})')
    # Requirement is a public domain label; attach it only during activation.
    staged_query = '\n'.join(line for line in staged_query.splitlines() if 'FOREACH' not in line)
    staged_query += '\n SET node.staged_requirement = row.requirement'
    resource_offset = receipt.get('resource_offset', 0)
    if (type(resource_offset) is not int or not 0 <= resource_offset <= len(resources)
            or (resource_offset != len(resources) and resource_offset % batch_size)):
        raise ValueError('Invalid retained publication checkpoint')
    for offset in range(resource_offset, len(resources), batch_size):
        rows = resources[offset:offset + batch_size]
        @transaction
        def write_resources(tx):
            tx.run(staged_query, rows=rows, **params, prefix=prefix,
                   updated_at=datetime.now(timezone.utc).isoformat(),
                   projection_revision=publication_id).consume()
            tx.run('MATCH (p:OntologyPublication {ontology_id:$ontology_id, publication_id:$publication_id}) '
                   'SET p.resource_offset=$offset', **params, offset=offset + len(rows)).consume()
        session.execute_write(write_resources)
        logging.getLogger(__name__).warning('Staged publication resources=%s/%s ontology_id=%s',
                                           offset + len(rows), len(resources), ontology_id)
    offsets = json.loads(receipt.get('relationship_offsets', '{}'))
    if not isinstance(offsets, dict):
        raise ValueError('Invalid retained relationship checkpoints')
    for relation_type, rows in relationships.items():
        offset = offsets.get(relation_type, 0)
        if (type(offset) is not int or not 0 <= offset <= len(rows)
                or (offset != len(rows) and offset % batch_size)):
            raise ValueError('Invalid retained relationship checkpoint')
        query = ('UNWIND $rows AS row '
                 'MATCH (source:StagedOntologyResource {ontology_id:$ontology_id, publication_id:$publication_id, iri:row.source}) '
                 'MATCH (target:StagedOntologyResource {ontology_id:$ontology_id, publication_id:$publication_id, iri:row.target}) '
                 + relation_queries[relation_type] + ' SET edge.publication_revision=$publication_id')
        for start in range(offset, len(rows), batch_size):
            batch = rows[start:start + batch_size]
            next_offsets = {**offsets, relation_type: start + len(batch)}
            @transaction
            def write_edges(tx):
                tx.run(query, rows=batch, **params).consume()
                tx.run('MATCH (p:OntologyPublication {ontology_id:$ontology_id, publication_id:$publication_id}) '
                       'SET p.relationship_offsets=$offsets', **params,
                       offsets=json.dumps(next_offsets, sort_keys=True)).consume()
            session.execute_write(write_edges)
            offsets = next_offsets
            logging.getLogger(__name__).warning('Staged publication relation=%s rows=%s/%s ontology_id=%s',
                                               relation_type, start + len(batch), len(rows), ontology_id)

    from .publication_activation import activate
    activation_budget = activation_timeout if activation_timeout is not None else timeout
    activation_budget += max(0, deadline - time.monotonic())
    activate(session, params=params, prefix=prefix, resources=resources,
             relationships=relationships, relation_queries=relation_queries,
             resource_query=resource_query, batch_size=batch_size,
             timeout=activation_budget, unit_of_work=unit_of_work)
    from .publication_cleanup import try_cleanup_completed_staging
    try_cleanup_completed_staging(session, **params, query_factory=query_factory)
    logging.getLogger(__name__).warning('Ontology publication phase=completed ontology_id=%s resources=%s relationships=%s',
        ontology_id, len(resources), total_relationships)
    return {'status': 'success', **params, 'resources': len(resources),
            'relationships': total_relationships,
            'hierarchy_edges': len(relationships['SUBCLASS_OF']) + len(relationships['HAS_PART'])}
