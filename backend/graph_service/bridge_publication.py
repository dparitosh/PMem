"""Atomic mapping publication and graph receipt under a stable publication ID."""
from backend.depo_platform.ontology_maintenance import ontology_writer
import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone

from backend.depo_platform.bridge_contract import digest


@contextmanager
def session():
    from neo4j import GraphDatabase
    from backend.depo_platform.neo4j_setup import _auth
    uri = os.getenv('NEO4J_URI') or os.getenv('NEO4J_URL')
    if not uri:
        raise RuntimeError('NEO4J_URI is required for Semantic Bridge publication')
    with GraphDatabase.driver(uri, auth=_auth(), connection_timeout=10, max_transaction_retry_time=0) as driver:
        with driver.session(database=os.getenv('NEO4J_DATABASE', 'neo4j')) as value:
            yield value


def receipt(publication_id):
    with session() as graph:
        row = graph.run(_bounded_query('MATCH (p:DepoBridgePublication {publication_id:$id}) RETURN p.receipt AS receipt'), id=publication_id).single()
        return json.loads(row['receipt']) if row and row['receipt'] else None


def _bounded_query(text):
    from neo4j import Query
    from backend.depo_platform.network import bounded_timeout_seconds
    from backend.depo_platform.operations import current_operation
    budget = bounded_timeout_seconds('GRAPH_PUBLICATION_TIMEOUT_SECONDS', default=180)
    operation = current_operation()
    return Query(text, timeout=operation.timeout(budget) if operation else budget)


@ontology_writer
def publish(command):
    expected = digest({k:v for k,v in command.items() if k != 'request_digest'})
    if expected != command.get('request_digest'):
        raise ValueError('Publication digest mismatch.')
    rows = command.get('rows')
    if not isinstance(rows, list) or not 1 <= len(rows) <= 2000:
        raise ValueError('Publication requires 1 to 2000 approved rows.')
    for row in rows:
        if not isinstance(row, dict) or not all(row.get(k) for k in ('candidate_id','import_id','import_row_key','ontology_class_element_id')) or row.get('target_ontology_type') not in {'Class','ObjectProperty','DatatypeProperty','AnnotationProperty'}:
            raise ValueError('Invalid approved mapping target or source.')
    with session() as graph:
        constraint = graph.run(
            _bounded_query('SHOW CONSTRAINTS YIELD name, type, entityType, labelsOrTypes, properties WHERE name = $name AND type IN [\'UNIQUENESS\', \'NODE_PROPERTY_UNIQUENESS\'] AND entityType = \'NODE\' AND labelsOrTypes = [\'DepoBridgePublication\'] AND properties = [\'publication_id\'] RETURN count(*) AS found'),
            name='depo_bridge_publication_id',
        ).single()
        if not constraint or constraint['found'] != 1:
            raise RuntimeError('Semantic Bridge publication constraint is missing. Run Neo4j schema provisioning before publishing.')
        from neo4j import unit_of_work
        from backend.depo_platform.network import bounded_timeout_seconds
        from backend.depo_platform.operations import current_operation
        timeout = bounded_timeout_seconds('GRAPH_PUBLICATION_TIMEOUT_SECONDS', default=180)
        operation = current_operation()
        if operation:
            timeout = operation.timeout(timeout)
        # Each request owns its decorator metadata; concurrent requests must not
        # mutate the timeout on the shared transaction function.
        def write(tx):
            return _publish_transaction(tx, command)
        return graph.execute_write(unit_of_work(timeout=timeout)(write))


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
        AND NOT target:RetainedOntologyIdentity
        AND NOT target:StagedOntologyResource
        AND (target.ontology_id=$ontology_id OR target.source_ontology=$ontology_id
          OR (target.ontology_id IS NULL
            AND (target.prefix=$ontology_id OR target.ontology_prefix=$ontology_id)))
        AND ((row.target_ontology_type='Class' AND target:OntologyClass)
          OR (row.target_ontology_type='ObjectProperty' AND target:ObjectProperty)
          OR (row.target_ontology_type='DatatypeProperty' AND target:DatatypeProperty)
          OR (row.target_ontology_type='AnnotationProperty' AND target:AnnotationProperty)
          OR (target:OntologyResource AND EXISTS {
            MATCH (target)-[rdfType:SEMANTIC_RELATION]->(type:OntologyResource)
            WHERE rdfType.predicate='http://www.w3.org/1999/02/22-rdf-syntax-ns#type'
              AND type.iri='http://www.w3.org/2002/07/owl#' + row.target_ontology_type
          }))
        AND (coalesce(row.target_ontology_iri,'')='' OR coalesce(target.iri,target.uri,target.resource_iri,'')=row.target_ontology_iri)
        WITH row, collect(DISTINCT n) AS sources, collect(DISTINCT target) AS targets
        RETURN row.candidate_id AS candidate_id, size(sources) AS sources, size(targets) AS targets''', rows=command['rows'], ontology_id=command['ontology_id']).data()
    if len(counts) != len(command['rows']) or any(c['sources'] != 1 or c['targets'] != 1 for c in counts):
        raise ValueError('Source or target changed or is ambiguous; no links were written.')
    written = tx.run('''UNWIND $rows AS row
        MATCH (n {import_row_key:row.import_row_key, import_id:row.import_id})
        MATCH (target) WHERE elementId(target)=row.ontology_class_element_id
        AND NOT target:RetainedOntologyIdentity
        AND NOT target:StagedOntologyResource
        AND (target.ontology_id=$ontology_id OR target.source_ontology=$ontology_id
          OR (target.ontology_id IS NULL
            AND (target.prefix=$ontology_id OR target.ontology_prefix=$ontology_id)))
        AND ((row.target_ontology_type='Class' AND target:OntologyClass)
          OR (row.target_ontology_type='ObjectProperty' AND target:ObjectProperty)
          OR (row.target_ontology_type='DatatypeProperty' AND target:DatatypeProperty)
          OR (row.target_ontology_type='AnnotationProperty' AND target:AnnotationProperty)
          OR (target:OntologyResource AND EXISTS {
            MATCH (target)-[rdfType:SEMANTIC_RELATION]->(type:OntologyResource)
            WHERE rdfType.predicate='http://www.w3.org/1999/02/22-rdf-syntax-ns#type'
              AND type.iri='http://www.w3.org/2002/07/owl#' + row.target_ontology_type
          }))
        AND (coalesce(row.target_ontology_iri,'')='' OR coalesce(target.iri,target.uri,target.resource_iri,'')=row.target_ontology_iri)
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
        WITH n, target, row
        MATCH (publication:DepoBridgePublication {publication_id:$id})
        MERGE (publication)-[:RECORDED_MAPPING]->(evidence:DepoBridgeMapping {publication_id:$id, candidate_id:row.candidate_id})
        SET evidence.mapping=row.mapping, evidence.mapping_type=row.mapping_type,
            evidence.confidence=row.confidence, evidence.approved_by=$actor,
            evidence.target_ontology_type=row.target_ontology_type,
            evidence.source_type=row.source_type, evidence.import_id=row.import_id,
            evidence.import_row_key=row.import_row_key, evidence.ontology_id=$ontology_id,
            evidence.target_iri=row.target_ontology_iri
        MERGE (evidence)-[:SOURCE]->(n)
        MERGE (evidence)-[:TARGET]->(target)
        RETURN count(*) AS applied
        ''', rows=command['rows'], id=publication_id, actor=command['approved_by'], ontology_id=command['ontology_id']).single()
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
    from backend.depo_platform.agent_memory_config import enabled as memory_enabled
    if memory_enabled():
        from backend.Services.agent_memory_service import AgentMemoryService
        facts = [AgentMemoryService._mapping_fact_row(command['ontology_id'], row['import_id'], row, publication_id) for row in command['rows']]
        tx.run('''UNWIND $rows AS row
            MERGE (f:AgentMemoryFact {fact_id:row.fact_id})
            ON CREATE SET f.created_at=$completed
            SET f.kind='semantic_bridge_mapping', f.scope=row.scope, f.source=row.source,
                f.source_type=row.source_type, f.target=row.target,
                f.target_iri=row.target_iri, f.generic_match=row.generic_match,
                f.target_type=row.target_type, f.ontology_id=row.ontology_id,
                f.import_task_id=row.import_task_id, f.confidence=row.confidence,
                f.mapping_type=row.mapping_type, f.task_id=row.task_id, f.updated_at=$completed''',
            rows=facts, completed=result['completed_at']).consume()
    return result
