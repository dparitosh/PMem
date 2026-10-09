"""Validated XML materialization through the approved data-job boundary.

Only the server-generated, supported XSD projection is executable. Existing
schemas are never altered; each schema closure gets its own versioned schema.
"""
from __future__ import annotations

import hashlib
import json
import re
import tempfile
import base64
from datetime import datetime, timezone
from pathlib import Path

from backend.artifact_store import ArtifactStore
from backend.mesh_store import PostgresRegistry
from backend.Services.schema_upload_paths import validate_schema_upload
from backend.Services.xsd_relational_report import build_xsd_relational_report, sql_name
from backend.Services.xsd_analytics_plan import build_analytics_schema_plan
from backend.depo_platform.execution_guard import ensure_execution_allowed
from .schema_limits import read_schema_bytes

MAX_BYTES = 25 * 1024 * 1024
MAX_ENTITIES = 100000


def prepare_xml_load(payload, artifacts=None):
    """Compile, validate and flatten before opening a database transaction."""
    try:
        from lxml import etree
    except ImportError as exc:
        raise RuntimeError('XML materialization requires the lxml schema-validation runtime') from exc
    store = artifacts or ArtifactStore()
    metadata, source = store.resolve(str(payload.get('schema_artifact_id') or ''))
    filename = str(metadata.get('filename') or '')
    if metadata.get('kind') != 'engineering-schema-source' or not filename.lower().endswith('.xsd'):
        raise ValueError('schema_artifact_id must reference a retained XSD schema')
    schema_content = read_schema_bytes(source)
    if metadata.get('sha256') and hashlib.sha256(schema_content).hexdigest() != metadata['sha256']:
        raise ValueError('Retained XSD source changed during reading')
    refs = payload.get('schema_dependencies', {})
    if not isinstance(refs, dict) or len(refs) > 63:
        raise ValueError('schema_dependencies must contain at most 63 relative paths')
    dependencies = {}
    remaining = MAX_BYTES - len(schema_content)
    for name, reference in refs.items():
        dependency_metadata, path = store.resolve(str(reference))
        if dependency_metadata.get('kind') != 'engineering-schema-source':
            raise ValueError('Dependencies must reference retained schema sources')
        dependencies[name] = read_schema_bytes(path, remaining_bytes=remaining)
        if dependency_metadata.get('sha256') and hashlib.sha256(dependencies[name]).hexdigest() != dependency_metadata['sha256']:
            raise ValueError('Retained schema dependency changed during reading')
        remaining -= len(dependencies[name])
    validate_schema_upload(filename, schema_content, dependencies)
    xml_metadata, xml_path = store.resolve(str(payload.get('xml_artifact_id') or ''))
    xml_content = read_schema_bytes(xml_path)
    if xml_metadata.get('sha256') and hashlib.sha256(xml_content).hexdigest() != xml_metadata['sha256']:
        raise ValueError('Retained XML instance changed during reading')
    # Entity expansion, DTDs and network resolution are forbidden before compilation.
    if any(marker in xml_content.replace(b'\x00', b'').upper() for marker in (b'<!DOCTYPE', b'<!ENTITY')):
        raise ValueError('XML DTDs and entity declarations are forbidden')
    with tempfile.TemporaryDirectory(prefix='depo-xml-load-') as temporary:
        root_path = Path(temporary) / filename
        root_path.write_bytes(schema_content)
        for name, content in dependencies.items():
            path = Path(temporary) / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        model = build_xsd_relational_report(root_path)
        if model['ddl_blockers']:
            raise ValueError('XML materialization blocked: ' + '; '.join(model['ddl_blockers']))
        parser = etree.XMLParser(resolve_entities=False, no_network=True)
        compiler = etree.XMLSchema(etree.parse(str(root_path), parser), attribute_defaults=True)
        try:
            document = etree.fromstring(xml_content, parser)
            compiler.assertValid(document)
        except (etree.XMLSyntaxError, etree.DocumentInvalid) as exc:
            raise ValueError('XML instance does not conform to the retained XSD closure') from exc
        canonical = etree.tostring(document, encoding='unicode')
        rows, links = flatten_xml(model, document)
    closure = {filename: hashlib.sha256(schema_content).hexdigest(),
               **{name: hashlib.sha256(content).hexdigest() for name, content in dependencies.items()}}
    digest = hashlib.sha256(json.dumps(closure, sort_keys=True).encode()).hexdigest()
    prefix = str(payload.get('schema_prefix') or 'depo_analytics')
    if not re.fullmatch(r'depo_analytics(?:_[a-z][a-z0-9_]{0,20})?', prefix):
        raise ValueError('schema_prefix must be depo_analytics or depo_analytics_<project>')
    schema = prefix + '_' + digest[:16]
    plan = build_analytics_schema_plan(model, schema=schema)
    business = payload.get('business_views', [])
    views = business_view_plan(model, schema, business)
    policy_digest = hashlib.sha256(json.dumps(business, sort_keys=True).encode()).hexdigest()
    return {'model': model, 'plan': plan, 'schema': schema, 'schema_digest': digest,
            'business_views': views, 'business_policy_digest': policy_digest,
            'xml_digest': hashlib.sha256(xml_content).hexdigest(), 'original_bytes': xml_content,
            'xml_document': canonical, 'rows': rows, 'links': links}


def business_view_plan(model, schema, definitions):
    """Explicit single-entity grains; never infer cross-entity joins or units."""
    if not isinstance(definitions, list) or len(definitions) > 20:
        raise ValueError('business_views must be a list of at most 20 definitions')
    tables = {table['entity_id']: table for table in model['tables']}
    statements, names = [], set()
    for definition in definitions:
        if not isinstance(definition, dict) or not isinstance(definition.get('name'), str) or not definition['name'].strip():
            raise ValueError('Each business view requires a name')
        entity = tables.get(definition.get('entity_id'))
        if entity is None or definition.get('grain') != 'entity-instance':
            raise ValueError('Business views require a known entity_id and grain entity-instance')
        columns = {column['name']: column for column in entity['columns']}
        groups, measures = definition.get('group_by', []), definition.get('measures', [])
        if not isinstance(groups, list) or any(not isinstance(name, str) or name not in columns for name in groups) or len(set(groups)) != len(groups):
            raise ValueError('group_by must contain unique known entity properties')
        if not isinstance(measures, list) or not measures or len(measures) > 30:
            raise ValueError('A business view requires 1–30 measures')
        expressions = [f'"{columns[name]["sql_name"]}" AS "{sql_name(name)}"' for name in groups]
        aliases = set(groups)
        for measure in measures:
            if not isinstance(measure, dict): raise ValueError('Invalid business measure')
            name, aggregate, property_name = measure.get('name'), measure.get('aggregate'), measure.get('property')
            if not isinstance(name, str) or not name.strip() or name in aliases or aggregate not in {'count', 'sum', 'avg', 'min', 'max'}:
                raise ValueError('Measure names must be unique and aggregate must be count/sum/avg/min/max')
            aliases.add(name)
            column = columns.get(property_name) if isinstance(property_name, str) else None
            if column is None and not (aggregate == 'count' and property_name is None):
                raise ValueError('Measure property is not in the selected entity')
            if aggregate in {'sum', 'avg'} and not (column and column['sql_type'] in {'NUMERIC', 'INTEGER', 'BIGINT', 'SMALLINT', 'REAL', 'DOUBLE PRECISION'}):
                raise ValueError('sum/avg require a numeric property')
            if aggregate in {'min', 'max'} and column['sql_type'] not in {'NUMERIC', 'INTEGER', 'BIGINT', 'SMALLINT', 'REAL', 'DOUBLE PRECISION', 'TEXT', 'DATE', 'TIME', 'TIMESTAMPTZ'}:
                raise ValueError('min/max require an ordered numeric, text or temporal property')
            operand = '*' if column is None else f'"{column["sql_name"]}"'
            expressions.append(f'{aggregate.upper()}({operand}) AS "{sql_name(name)}"')
        view = sql_name('business:' + definition['name'])
        if view in names: raise ValueError('Duplicate business view name')
        names.add(view)
        group_clause = ' GROUP BY ' + ','.join(f'"{columns[name]["sql_name"]}"' for name in groups) if groups else ''
        statements.append({'name': definition['name'], 'view': view,
            'sql': f'CREATE VIEW "{schema}"."{view}" AS SELECT ' + ','.join(expressions) + f' FROM "{schema}"."{entity["sql_name"]}"' + group_clause})
    return statements


def flatten_xml(model, document):
    """Preserve namespace identity, repeated scalar values and child order."""
    tables = {table['entity_id']: table for table in model['tables']}
    roots = [root for root in model['roots'] if root['source_qname'] == document.tag]
    if len(roots) != 1:
        raise ValueError('XML root has no unique structural projection')
    rows, links = [], []
    def visit(entity_id, node):
        if len(rows) >= MAX_ENTITIES:
            raise ValueError('XML instance exceeds the entity materialization limit')
        table = tables[entity_id]
        values = []
        nil = node.get('{http://www.w3.org/2001/XMLSchema-instance}nil') in {'true', '1'}
        for column in table['columns']:
            if table['source_kind'] in {'repeated scalar', 'scalar root'}:
                value = None if nil else (node.text or '')
            elif column['source_kind'] == 'attribute':
                value = node.get(column['source_qname'])
            else:
                children = [child for child in node if child.tag == column['source_qname']]
                if len(children) > 1:
                    raise ValueError('Scalar projection received multiple matching children')
                value = None if not children or children[0].get('{http://www.w3.org/2001/XMLSchema-instance}nil') in {'true', '1'} else (children[0].text or '')
            # XSD defaults apply to present empty elements, never absent or nil ones.
            if value == '' and column.get('source_kind') != 'attribute' and column.get('default') is not None:
                value = column['default']
            datatype = column.get('resolved_type', '').rsplit('}', 1)[-1]
            if value is not None and datatype == 'normalizedString':
                value = value.replace('\t', ' ').replace('\r', ' ').replace('\n', ' ')
            if value is not None and datatype == 'token': value = ' '.join(value.split())
            if value is not None and column.get('sql_type') in {'REAL', 'DOUBLE PRECISION'}: value = float(value)
            if value is not None and column.get('sql_type') == 'BYTEA':
                value = bytes.fromhex(value) if datatype == 'hexBinary' else base64.b64decode(''.join(value.split()), validate=True)
            values.append(value)
        index = len(rows)
        rows.append((entity_id, values))
        for ordinal, relationship in enumerate(table['relationships']):
            children = [child for child in node if child.tag == relationship['source_qname']]
            low, high = relationship['min_occurs'], relationship['max_occurs']
            if len(children) < low or (high != 'unbounded' and len(children) > high):
                raise ValueError('XML relationship cardinality mismatch')
            for position, child in enumerate(children):
                links.append((entity_id, ordinal, index, visit(relationship['target_entity_id'], child), position))
        return index
    visit(roots[0]['entity_id'], document)
    return rows, links


def materialize_xml(payload, *, correlation_id):
    prepared = prepare_xml_load(payload)
    registry = PostgresRegistry('xml_analytics_loads')
    key = prepared['schema'] + ':' + prepared['xml_digest'] + ':' + prepared['business_policy_digest']
    from psycopg import sql
    from psycopg.types.json import Jsonb
    tables = {table['entity_id']: table for table in prepared['model']['tables']}
    ensure_execution_allowed()
    with registry._connect() as db, db.transaction(), db.cursor() as cursor:
        cursor.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', (prepared['schema'],))
        cursor.execute('SELECT value FROM depo_registry WHERE namespace=%s AND key=%s', (registry.namespace, key))
        previous = cursor.fetchone()
        if previous:
            return previous[0]
        cursor.execute('SELECT value FROM depo_registry WHERE namespace=%s AND key=%s', ('xml_analytics_schemas', prepared['schema']))
        known = cursor.fetchone()
        if not known:
            # The server-generated plan comes only from a compiled XSD with no blockers.
            # CREATE (without IF NOT EXISTS) fails closed for untracked schemas.
            for statement in prepared['plan']['sql'].split(';'):
                if statement.strip(): cursor.execute(statement)
            cursor.execute(sql.SQL('CREATE TABLE {}.source_documents (sha256 TEXT PRIMARY KEY, original_bytes BYTEA NOT NULL, document XML NOT NULL, metadata JSONB NOT NULL)').format(sql.Identifier(prepared['schema'])))
            for table in tables.values():
                cursor.execute(sql.SQL('ALTER TABLE {}.{} ADD COLUMN source_document_sha256 TEXT NOT NULL REFERENCES {}.source_documents(sha256)').format(sql.Identifier(prepared['schema']), sql.Identifier(table['sql_name']), sql.Identifier(prepared['schema'])))
            for view in prepared['business_views']: cursor.execute(view['sql'])
            cursor.execute('INSERT INTO depo_registry(namespace,key,value) VALUES (%s,%s,%s)',
                           ('xml_analytics_schemas', prepared['schema'], Jsonb({'schema_digest': prepared['schema_digest'], 'business_policy_digest': prepared['business_policy_digest'], 'model': prepared['model']})))
        elif known[0]['schema_digest'] != prepared['schema_digest'] or known[0].get('model') != prepared['model']:
            raise ValueError('Existing analytics schema differs; use a new versioned projection')
        elif known[0].get('business_policy_digest') != prepared['business_policy_digest']:
            raise ValueError('Business definitions differ from the retained projection; use a different schema_prefix')
        receipt = {'status': 'completed', 'job_type': 'xml-analytics-materialize', 'schema': prepared['schema'],
                   'execution_actor': payload.get('execution_actor'), 'loaded_at': datetime.now(timezone.utc).isoformat(),
                   'schema_digest': prepared['schema_digest'], 'xml_digest': prepared['xml_digest'],
                   'correlation_id': correlation_id, 'counts': {'entities': len(prepared['rows']), 'relationships': len(prepared['links']), 'source_documents': 1},
                   'business_views': [{key: value for key, value in view.items() if key != 'sql'} for view in prepared['business_views']],
                   'analytics_readiness': 'explicit-business-views-available' if prepared['business_views'] else 'structural-data-loaded; business-metrics-not-defined'}
        cursor.execute(sql.SQL('INSERT INTO {}.source_documents VALUES (%s,%s,XMLPARSE(DOCUMENT %s),%s)').format(sql.Identifier(prepared['schema'])),
                       (prepared['xml_digest'], prepared['original_bytes'], prepared['xml_document'], Jsonb(receipt)))
        identities = []
        for row_index, (entity_id, values) in enumerate(prepared['rows']):
            if row_index % 100 == 0: ensure_execution_allowed()
            table = tables[entity_id]
            if values:
                query = sql.SQL('INSERT INTO {}.{} ({}) VALUES ({}) RETURNING instance_id').format(
                    sql.Identifier(prepared['schema']), sql.Identifier(table['sql_name']),
                    sql.SQL(',').join([*(sql.Identifier(column['sql_name']) for column in table['columns']), sql.Identifier('source_document_sha256')]),
                    sql.SQL(',').join(sql.Placeholder() for _ in [*values, prepared['xml_digest']]))
                cursor.execute(query, [*values, prepared['xml_digest']])
            else:
                cursor.execute(sql.SQL('INSERT INTO {}.{} (source_document_sha256) VALUES (%s) RETURNING instance_id').format(sql.Identifier(prepared['schema']), sql.Identifier(table['sql_name'])), (prepared['xml_digest'],))
            identities.append(cursor.fetchone()[0])
        for link_index, (entity_id, ordinal, parent, child, position) in enumerate(prepared['links']):
            if link_index % 100 == 0: ensure_execution_allowed()
            relationship = tables[entity_id]['relationships'][ordinal]
            name = sql_name(entity_id + '/' + relationship['name'] + '/' + str(ordinal) + '/link')
            cursor.execute(sql.SQL('INSERT INTO {}.{} (owner_id,child_id,position) VALUES (%s,%s,%s)').format(sql.Identifier(prepared['schema']), sql.Identifier(name)), (identities[parent], identities[child], position))
        ensure_execution_allowed()
        cursor.execute('INSERT INTO depo_registry(namespace,key,value) VALUES (%s,%s,%s)', (registry.namespace, key, Jsonb(receipt)))
    return receipt
