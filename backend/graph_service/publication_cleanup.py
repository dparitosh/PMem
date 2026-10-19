"""Discard disposable staging copies only after verified activation."""
import logging
import time


def cleanup_completed_staging(session, *, ontology_id, publication_id, timeout=30, query_factory=None):
    params = {'ontology_id': ontology_id, 'publication_id': publication_id}
    deadline = time.monotonic() + timeout

    def statement(text):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('Completed publication staging cleanup deadline exceeded')
        return query_factory(text, timeout=min(10, remaining)) if query_factory else text

    receipt = session.run(statement(
        'MATCH (p:OntologyPublication {ontology_id:$ontology_id, publication_id:$publication_id}) '
        "WHERE p.status='published' AND p.current=true "
        'RETURN p.resources AS resources, p.relationships AS relationships'), **params).single()
    if not receipt:
        return 0  # Active, failed and superseded attempts retain their checkpoints.
    counts = session.run(statement(
        'MATCH (n:OntologyResource {ontology_id:$ontology_id}) '
        'WITH count(n) AS resources '
        'OPTIONAL MATCH (a:OntologyResource {ontology_id:$ontology_id})-[r]->'
        '(b:OntologyResource {ontology_id:$ontology_id}) '
        'WHERE r.ontology_id=$ontology_id AND r.publication_revision=$publication_id '
        'RETURN resources, count(r) AS relationships'), **params).single()
    if not counts or any(counts[key] != receipt[key] for key in ('resources', 'relationships')):
        raise ValueError('Published graph counts differ from receipt; staging retained for reconciliation')

    removed = 0
    from neo4j import unit_of_work
    while True:
        query = (
            'MATCH (p:OntologyPublication {ontology_id:$ontology_id, publication_id:$publication_id}) '
            "WHERE p.status='published' AND p.current=true "
            'MATCH (n:StagedOntologyResource {ontology_id:$ontology_id, publication_id:$publication_id}) '
            'WITH n LIMIT 1000 DETACH DELETE n RETURN count(*) AS removed')
        def delete_batch(tx):
            return tx.run(query, **params).single()['removed']
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('Completed publication staging cleanup deadline exceeded')
        count = session.execute_write(unit_of_work(timeout=min(10, remaining))(delete_batch))
        removed += count
        if count < 1000:
            return removed


def try_cleanup_completed_staging(session, **kwargs):
    # Activation has already committed. A cleanup problem must not turn a
    # successfully published ontology into a failed publication job.
    try:
        return cleanup_completed_staging(session, **kwargs)
    except Exception:
        logging.getLogger(__name__).exception('Completed publication staging cleanup deferred')
        return None
