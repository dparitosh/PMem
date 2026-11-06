"""Discover and preview only receipt-backed analytics; never execute client SQL."""
import json
import re
import logging
from backend.Services.xsd_relational_report import sql_name
from psycopg import Error as DatabaseError
from fastapi import APIRouter, Depends, HTTPException, Query
from backend.depo_platform.authorization import graph_read_identity
from backend.mesh_store import PostgresRegistry

router = APIRouter(prefix='/pipeline/analytics', tags=['Available analytics'], dependencies=[Depends(graph_read_identity)])
_SCHEMA = re.compile(r'[a-z_][a-z0-9_]{0,62}')
_WHERE = "namespace='data_job_runs' AND value->>'job_type'='xml-analytics-materialize' AND value->>'status'='completed' AND value#>>'{output_manifest,ods_receipt,status}'='completed'"
_VALID = " AND value#>>'{output_manifest,ods_receipt,schema}' ~ '^[a-z_][a-z0-9_]{0,62}$' AND jsonb_typeof(value->'run_id')='string' AND value->>'run_id' ~ '^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$'"
_PATH = "value#>>'{output_manifest,ods_receipt,schema}'"


def summary(run):
    receipt = (run.get('output_manifest') or {}).get('ods_receipt') or {}
    return {'run_id': run['run_id'], 'schema': receipt['schema'], 'loaded_at': receipt.get('loaded_at'),
            'readiness': receipt.get('analytics_readiness'), 'latest_load_counts': receipt.get('counts', {}),
            'business_views': receipt.get('business_views', []), 'quality_status': run.get('quality_status') or 'not_recorded',
            'evidence_status': (run.get('output_manifest') or {}).get('evidence_status', 'not_recorded'),
            'publication_status': 'not_established_by_load',
            'review_url': '/#/data-products?run_id=' + run['run_id']}


def inventory(limit, offset):
    # Deduplicate retries/loads into their versioned physical schema. Latest-load
    # counts are not presented as total dataset row counts.
    with PostgresRegistry('data_job_runs')._connect() as db, db.transaction(), db.cursor() as cursor:
        cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
        cursor.execute("SET LOCAL statement_timeout = '5s'")
        cursor.execute('SELECT count(DISTINCT (' + _PATH + ')) FROM depo_registry WHERE ' + _WHERE + _VALID)
        total = cursor.fetchone()[0]
        cursor.execute('SELECT value FROM (SELECT DISTINCT ON (' + _PATH + ') value, updated_at, key FROM depo_registry WHERE '
                       + _WHERE + _VALID + ' ORDER BY ' + _PATH + ', updated_at DESC, key DESC) latest ORDER BY updated_at DESC, key DESC LIMIT %s OFFSET %s', (limit, offset))
        rows = []
        for row in cursor.fetchall():
            record=row[0]
            receipt=(record.get('output_manifest') or {}).get('ods_receipt') or {}
            if not isinstance(receipt,dict) or not isinstance(receipt.get('schema'),str) or not _SCHEMA.fullmatch(receipt['schema']) or not isinstance(record.get('run_id'),str):
                logging.getLogger(__name__).warning('Excluded malformed analytics inventory receipt')
                continue
            rows.append(summary(record))
    return {'datasets': rows, 'total': total, 'limit': limit, 'offset': offset,
            'next_offset': offset + limit if offset + limit < total else None,
            'scope': 'Completed, receipt-backed XML analytics schemas; external databases and unregistered tables are not counted.'}


def retained(run_id):
    run = PostgresRegistry('data_job_runs').get(run_id)
    if not run or run.get('run_id') != run_id or run.get('status') != 'completed' or run.get('job_type') != 'xml-analytics-materialize':
        raise HTTPException(404, 'Completed analytics run not found')
    receipt = (run.get('output_manifest') or {}).get('ods_receipt') or {}
    schema = receipt.get('schema', '')
    if receipt.get('status') != 'completed' or not isinstance(schema, str) or not _SCHEMA.fullmatch(schema):
        raise HTTPException(409, 'A committed analytics receipt is required')
    owned = PostgresRegistry('xml_analytics_schemas').get(schema)
    if not owned or not receipt.get('schema_digest') or owned.get('schema_digest') != receipt.get('schema_digest') or not isinstance(owned.get('model'), dict):
        raise HTTPException(409, 'Analytics ownership or schema version could not be verified')
    return run, receipt, owned['model']


def relations(receipt, model):
    tables = [{'name': table['sql_name'], 'label': table.get('name') or table['entity_id'],
               'kind': 'operational table', 'grain': 'validated entity instance', 'entity_id': table['entity_id']}
              for table in model.get('tables', [])]
    links=[{'name':sql_name(table['entity_id']+'/'+link['name']+'/'+str(index)+'/link'),
            'label':(table.get('name') or table['entity_id'])+' / '+link['name'],
            'kind':'relationship table','grain':'ordered parent-child association',
            'entity_id':table['entity_id'],'target_entity_id':link.get('target_entity_id'),
            'keys':['owner_id','position'],'attributes':['child_id']}
           for table in model.get('tables',[]) for index,link in enumerate(table.get('relationships',[]))]
    return tables + links + [{'name': view['view'], 'label': view['name'], **{key: view.get(key) for key in
                      ('kind', 'grain', 'keys', 'attributes', 'group_by', 'output_columns', 'unit', 'description')}}
                     for view in receipt.get('business_views', [])]


def inspect(run_id, relation=None, limit=25):
    from psycopg import sql
    run, receipt, model = retained(run_id)
    owned_relations = relations(receipt, model)
    selected = next((r for r in owned_relations if r['name'] == relation), None) if relation else None
    if relation and not selected:
        raise HTTPException(404, 'The requested table or view is not part of this retained analytics projection')
    with PostgresRegistry('xml_analytics_schemas')._connect() as db, db.transaction(), db.cursor() as cursor:
        cursor.execute('SET TRANSACTION READ ONLY')
        cursor.execute("SET LOCAL statement_timeout = '5s'")
        cursor.execute("SELECT c.relname, a.attname, format_type(a.atttypid,a.atttypmod) FROM pg_catalog.pg_class c "
                       "JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace JOIN pg_catalog.pg_attribute a ON a.attrelid=c.oid "
                       "WHERE n.nspname=%s AND c.relname=ANY(%s) AND c.relkind IN ('r','p','v','m') "
                       "AND a.attnum>0 AND NOT a.attisdropped ORDER BY c.relname,a.attnum",
                       (receipt['schema'], [relation] if relation else [r['name'] for r in owned_relations[:200]]))
        columns = {}
        for name, field, type_name in cursor.fetchall():
            columns.setdefault(name, []).append({'name': field, 'type': type_name})
        if relation:
            selected_columns = [c for c in columns.get(relation, []) if c['name'] != 'source_document_sha256'][:30]
            if not selected_columns:
                raise HTTPException(409, 'The retained analytics relation is missing or has no readable columns')
            # Format and bound every cell in PostgreSQL before fetching it. No
            # XML/source byte tables, arbitrary SQL, COUNT scans or write path.
            fields = sql.SQL(',').join(sql.SQL('left({}::text,1000)').format(sql.Identifier(c['name'])) for c in selected_columns)
            cursor.execute(sql.SQL('SELECT {} FROM {}.{} LIMIT %s').format(fields, sql.Identifier(receipt['schema']), sql.Identifier(relation)), (limit + 1,))
            fetched = cursor.fetchall()
            rows, size = [], 0
            for row in fetched[:limit]:
                size += len(json.dumps(row).encode('utf-8'))
                if size > 262144:
                    break
                rows.append(list(row))
            return {'schema': receipt['schema'], 'relation': relation, 'columns': selected_columns, 'rows': rows,
                    'limited': len(fetched) > limit or len(rows) < len(fetched[:limit]), 'ordered': False,
                    'cell_character_limit': 1000, 'read_only': True}
    described = [{**r, 'available': r['name'] in columns, 'columns': columns.get(r['name'], [])[:100],
                  'column_count': len(columns.get(r['name'], []))} for r in owned_relations[:200]]
    return {**summary(run), 'relations': described, 'relation_total': len(owned_relations),
            'relations_limited': len(owned_relations) > 200,
            'evidence_ready': (run.get('output_manifest') or {}).get('evidence_status') == 'available',
            'consumption': 'Read-only preview; qualified SQL tables/views for authorized database consumers. Publication and access provisioning remain separate.'}


@router.get('')
def available_analytics(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    try:
        return inventory(limit, offset)
    except (DatabaseError, RuntimeError, OSError):
        raise HTTPException(503, 'Analytics inventory is unavailable; retry after checking the pipeline registry') from None


@router.get('/{run_id}')
def analytics_details(run_id: str):
    try:
        return inspect(run_id)
    except (DatabaseError, RuntimeError, OSError):
        raise HTTPException(503, 'Analytics metadata is unavailable; retry after checking the pipeline registry') from None


@router.get('/{run_id}/data')
def analytics_preview(run_id: str, relation: str = Query(min_length=1, max_length=128), limit: int = Query(25, ge=1, le=50)):
    try:
        return inspect(run_id, relation, limit)
    except (DatabaseError, RuntimeError, OSError):
        raise HTTPException(503, 'Analytics preview is unavailable; refresh the retained dataset before retrying') from None
