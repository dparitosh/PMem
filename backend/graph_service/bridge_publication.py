"""Atomic mapping publication and graph receipt under a stable publication ID."""
import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone

from backend.agentic_service.bridge_jobs import digest


@contextmanager
def session():
    from neo4j import GraphDatabase
    with GraphDatabase.driver(os.environ['NEO4J_URI'], auth=(os.environ['NEO4J_USER'], os.environ['NEO4J_PASS'])) as driver:
        with driver.session(database=os.environ['NEO4J_DATABASE']) as value:
            yield value


def receipt(publication_id):
    with session() as graph:
        row = graph.run('MATCH (p:DepoBridgePublication {publication_id:$id}) RETURN p.receipt AS receipt', id=publication_id).single()
        return json.loads(row['receipt']) if row and row['receipt'] else None


def publish(command):
    expected = digest({k:v for k,v in command.items() if k != 'request_digest'})
    if expected != command.get('request_digest'):
        raise ValueError('Publication digest mismatch.')
    rows = command.get('rows')
    if not isinstance(rows, list) or not 1 <= len(rows) <= 2000:
        raise ValueError('Publication requires 1 to 2000 approved rows.')
    for row in rows:
        if not all(row.get(k) for k in ('candidate_id','import_id','import_row_key','ontology_class_element_id')) or row.get('target_ontology_type') not in {'Class','ObjectProperty','DatatypeProperty','AnnotationProperty'}:
            raise ValueError('Invalid approved mapping target or source.')
    with session() as graph:
        graph.run('CREATE CONSTRAINT depo_bridge_publication_id IF NOT EXISTS FOR (p:DepoBridgePublication) REQUIRE p.publication_id IS UNIQUE').consume()
        return graph.execute_write(_publish_transaction, command)


def _publish_transaction(tx, command):
    publication_id = command['publication_id']
    state = tx.run('''MERGE (p:DepoBridgePublication {publication_id:$id})
        SET p.lock_version=coalesce(p.lock_version,0)+1
        RETURN p.receipt AS receipt, p.request_digest AS digest''', id=publication_id).single()
    if state['receipt']:
        if state['digest'] != command['request_digest']:
            raise ValueError('Publication ID already belongs to another approval.')
        return json.loads(state['receipt'])
    counts = tx.run('''UNWIND $rows AS row
        MATCH (n {import_row_key:row.import_row_key, import_id:row.import_id})
        MATCH (target) WHERE elementId(target)=row.ontology_class_element_id
        AND (coalesce(row.target_ontology_iri,'')='' OR coalesce(target.iri,target.uri,target.resource_iri,'')=row.target_ontology_iri)
        WITH row, collect(DISTINCT n) AS sources, collect(DISTINCT target) AS targets
        RETURN row.candidate_id AS candidate_id, size(sources) AS sources, size(targets) AS targets''', rows=command['rows']).data()
    if len(counts) != len(command['rows']) or any(c['sources'] != 1 or c['targets'] != 1 for c in counts):
        raise ValueError('Source or target changed or is ambiguous; no links were written.')
    written = tx.run('''UNWIND $rows AS row
        MATCH (n {import_row_key:row.import_row_key, import_id:row.import_id})
        MATCH (target) WHERE elementId(target)=row.ontology_class_element_id
        MERGE (n)-[bridge:SEMANTICALLY_MAPPED_TO]->(target)
        SET bridge.mapping=row.mapping, bridge.ontology_term=row.ontology_term,
            bridge.target_ontology_type=row.target_ontology_type, bridge.source_type=row.source_type,
            bridge.confidence=row.confidence, bridge.mapping_type=row.mapping_type,
            bridge.validation_status='approved', bridge.import_id=row.import_id,
            bridge.linked_by='semantic_bridge', bridge.publication_id=$id, bridge.approved_by=$actor
        FOREACH (_ IN CASE WHEN row.target_ontology_type='Class' THEN [1] ELSE [] END |
            MERGE (n)-[inst:INSTANCE_OF]->(target)
            SET inst.mapping=row.mapping, inst.class_name=row.ontology_term,
                inst.import_id=row.import_id, inst.linked_by='semantic_bridge', inst.publication_id=$id)
        RETURN count(*) AS applied
        ''', rows=command['rows'], id=publication_id, actor=command['approved_by']).single()
    if not written or written['applied'] != len(command['rows']):
        raise ValueError('Graph changed during publication; transaction rolled back.')
    result = {'publication_id': publication_id, 'request_digest': command['request_digest'],
              'applied_links': len(command['rows']), 'approved_by': command['approved_by'],
              'completed_at': datetime.now(timezone.utc).isoformat()}
    # Receipt and durable change event commit with the links. Consumers can read
    # the event by publication_id; retries do not create duplicate notifications.
    tx.run('''MATCH (p:DepoBridgePublication {publication_id:$id})
        SET p.request_digest=$digest, p.receipt=$receipt
        MERGE (p)-[:EMITTED]->(e:DepoBridgeChange {publication_id:$id})
        SET e.kind='Modification', e.preview_id=$preview, e.created_at=$completed''',
        id=publication_id, digest=command['request_digest'], receipt=json.dumps(result),
        preview=command['preview_id'], completed=result['completed_at']).consume()
    if os.getenv('AGENT_MEMORY_ENABLED', '').lower() == 'true':
        tx.run('''UNWIND $rows AS row
            MERGE (f:AgentMemoryFact {fact_id:$id+':'+row.candidate_id})
            SET f.kind='semantic_bridge_mapping', f.source=row.source_term,
                f.source_type=row.source_type, f.target=row.ontology_term,
                f.target_type=row.target_ontology_type, f.ontology_id=$ontology,
                f.import_task_id=row.import_id, f.confidence=row.confidence,
                f.mapping_type=row.mapping_type, f.task_id=$id, f.updated_at=$completed''',
            rows=command['rows'], id=publication_id, ontology=command['ontology_id'], completed=result['completed_at']).consume()
    return result
