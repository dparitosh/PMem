"""Bounded activation transactions under the durable graph access barrier."""
import json
import time
from functools import wraps
from datetime import datetime, timezone

from backend.depo_platform.graph_access import replacement_access
from backend.depo_platform.operations import current_operation


def activate(session, *, params, prefix, resources, relationships, relation_queries,
             resource_query, batch_size, timeout, unit_of_work):
    deadline = time.monotonic() + timeout

    def commit(operation, *, fenced=False):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('Publication activation deadline reached; resume retained checkpoints')
        operation_context = current_operation()
        budget = min(30, remaining)
        if operation_context:
            budget = operation_context.timeout(budget)
        @wraps(operation)
        def guarded(tx):
            if fenced:
                # Acquire the receipt's Neo4j write lock BEFORE checking owner.
                # A stale owner then rolls back this transaction without touching
                # public nodes, even if its PostgreSQL lock connection was lost.
                tx.run(
                    'MATCH (p:OntologyPublication {ontology_id:$ontology_id, publication_id:$publication_id}) '
                    'SET p.activation_fence=coalesce(p.activation_fence,0)+1', **params).consume()
                owner = tx.run(
                    'MATCH (p:OntologyPublication {ontology_id:$ontology_id, publication_id:$publication_id}) '
                    "WHERE p.activation_owner=$owner_id AND p.status='staging' "
                    'RETURN p.activation_owner AS owner', **params, owner_id=activation.owner_id).single()
                if not owner:
                    raise RuntimeError('Graph activation owner changed or publication already completed')
            return operation(tx)
        return session.execute_write(unit_of_work(timeout=budget)(guarded))

    with replacement_access(params['ontology_id'], params['publication_id'], deadline=deadline) as activation:
        def load(tx):
            tx.run('MATCH (p:OntologyPublication {ontology_id:$ontology_id, publication_id:$publication_id}) '
                   'SET p.activation_owner=$owner_id', **params, owner_id=activation.owner_id).consume()
            return dict(tx.run('MATCH (p:OntologyPublication {ontology_id:$ontology_id, publication_id:$publication_id}) '
                               'RETURN p {.*} AS receipt', **params).single()['receipt'])
        receipt = commit(load)
        if receipt.get('status') == 'published' and receipt.get('current') is True:
            return  # Reconcile a lost response after the graph commit.

        def validate(tx):
            nodes = tx.run('MATCH (n:StagedOntologyResource {ontology_id:$ontology_id, publication_id:$publication_id}) '
                           'RETURN count(n) AS count', **params).single()['count']
            edges = tx.run('MATCH (a:StagedOntologyResource {ontology_id:$ontology_id, publication_id:$publication_id})'
                           '-[r]->(b:StagedOntologyResource {ontology_id:$ontology_id, publication_id:$publication_id}) '
                           'WHERE r.ontology_id=$ontology_id AND r.publication_revision=$publication_id '
                           'RETURN count(r) AS count', **params).single()['count']
            if nodes != len(resources) or edges != sum(map(len, relationships.values())):
                raise ValueError('Staged projection counts do not match its manifest; activation refused')
        commit(validate)
        copy_query = resource_query.replace('UNWIND $rows AS row',
            'UNWIND $iris AS iri '
            'MATCH (staged:StagedOntologyResource {ontology_id:$ontology_id, publication_id:$publication_id, iri:iri}) '
            'WITH staged {.*, requirement: staged.staged_requirement} AS row')
        if copy_query == resource_query:
            raise ValueError('Resource query is incompatible with replacement activation')
        offset = receipt.get('activation_resource_offset', 0)
        _offset(offset, len(resources), batch_size)
        for start in range(offset, len(resources), batch_size):
            iris = [row['iri'] for row in resources[start:start + batch_size]]
            activation.begin_mutation()
            def copy(tx):
                tx.run('UNWIND $iris AS iri MATCH (n:RetainedOntologyIdentity {ontology_id:$ontology_id, iri:iri}) '
                       'SET n:OntologyResource REMOVE n:RetainedOntologyIdentity', **params, iris=iris).consume()
                tx.run(copy_query, **params, iris=iris, prefix=prefix,
                       updated_at=datetime.now(timezone.utc).isoformat(),
                       projection_revision=params['publication_id']).consume()
                tx.run('MATCH (p:OntologyPublication {ontology_id:$ontology_id, publication_id:$publication_id}) '
                       'SET p.activation_resource_offset=$offset', **params, offset=start + len(iris)).consume()
            commit(copy, fenced=True)
        offsets = json.loads(receipt.get('activation_relationship_offsets', '{}'))
        if not isinstance(offsets, dict):
            raise ValueError('Invalid activation relationship checkpoints')
        for kind, rows in relationships.items():
            offset = offsets.get(kind, 0)
            _offset(offset, len(rows), batch_size)
            query = ('UNWIND $rows AS row '
                'MATCH (source:OntologyResource {ontology_id:$ontology_id, iri:row.source}) '
                'MATCH (target:OntologyResource {ontology_id:$ontology_id, iri:row.target}) '
                + relation_queries[kind] + ' SET edge.publication_revision=$projection_revision')
            for start in range(offset, len(rows), batch_size):
                batch = rows[start:start + batch_size]
                next_offsets = {**offsets, kind: start + len(batch)}
                activation.begin_mutation()
                def edges(tx):
                    tx.run(query, **params, rows=batch, projection_revision=params['publication_id']).consume()
                    tx.run('MATCH (p:OntologyPublication {ontology_id:$ontology_id, publication_id:$publication_id}) '
                           'SET p.activation_relationship_offsets=$offsets', **params,
                           offsets=json.dumps(next_offsets, sort_keys=True)).consume()
                commit(edges, fenced=True)
                offsets = next_offsets

        cleanup = [
            ('MATCH (a:OntologyResource {ontology_id:$ontology_id})-[edge]->(b:OntologyResource {ontology_id:$ontology_id}) '
             'WHERE edge.ontology_id=$ontology_id AND type(edge) IN $types '
             'AND (edge.publication_revision IS NULL OR edge.publication_revision <> $publication_id) '
             'WITH edge LIMIT $batch_size DELETE edge RETURN count(*) AS count'),
            ('MATCH (n:OntologyResource {ontology_id:$ontology_id}) '
             'WHERE n.publication_revision IS NULL OR n.publication_revision <> $publication_id '
             'WITH n LIMIT $batch_size REMOVE n:OntologyResource SET n:RetainedOntologyIdentity REMOVE n:Requirement '
             'RETURN count(*) AS count'),
            ('MATCH (n:RetainedOntologyIdentity {ontology_id:$ontology_id}) WHERE NOT (n)--() '
             'WITH n LIMIT $batch_size DELETE n RETURN count(*) AS count'),
        ]
        for query in cleanup:
            while True:
                activation.begin_mutation()
                def clean(tx):
                    return tx.run(query, **params, batch_size=batch_size, types=list(relationships)).single()['count']
                if commit(clean, fenced=True) < batch_size:
                    break

        def finish(tx):
            tx.run('MATCH (p:OntologyPublication {ontology_id:$ontology_id}) SET p.current=false',
                   ontology_id=params['ontology_id']).consume()
            tx.run('MATCH (p:OntologyPublication {ontology_id:$ontology_id, publication_id:$publication_id}) '
                   "SET p.status='published', p.current=true, p.prefix=$prefix, p.resources=$resources, "
                   'p.relationships=$relationships, p.hierarchy_edges=$hierarchy_edges, p.published_at=$published_at',
                   **params, prefix=prefix, resources=len(resources), relationships=sum(map(len, relationships.values())),
                   hierarchy_edges=len(relationships['SUBCLASS_OF']) + len(relationships['HAS_PART']),
                   published_at=datetime.now(timezone.utc).isoformat()).consume()
        commit(finish, fenced=True)


def _offset(value, total, batch_size):
    if type(value) is not int or not 0 <= value <= total or (value != total and value % batch_size):
        raise ValueError('Invalid retained activation checkpoint')
