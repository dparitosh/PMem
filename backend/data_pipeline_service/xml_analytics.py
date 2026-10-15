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
from .analytics_fields import resolve_property, numeric_type

MAX_BYTES = 25 * 1024 * 1024
MAX_ENTITIES = 100000


def prepare_xml_load(payload, artifacts=None):
    """Compile, validate and flatten before opening a database transaction."""
    try:
        from lxml import etree
    except ImportError as exc:
        raise RuntimeError('XML materialization requires the lxml schema-validation runtime') from exc
    binding = payload.get('business_schema_artifact_id')
    if binding and binding != payload.get('schema_artifact_id'):
        raise ValueError('Business view definitions belong to another schema artifact; reload schema fields')
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
        policy = payload.get('constraint_policy', 'strict')
        if policy not in {'strict', 'validated-source'}:
            raise ValueError('constraint_policy must be strict or validated-source')
        if policy == 'validated-source':
            # The complete XML is still formally validated below. These source
            # constraints are not claimed as PostgreSQL constraint definitions.
            permitted = {'Datatype facets require validated instance loading and constraint review',
                         'Fixed values require source validation and SQL constraint review'}
            model['ddl_blockers'] = [reason for reason in model['ddl_blockers'] if reason not in permitted]
            for table in model['tables']:
                for column in table['columns']:
                    # XSD totalDigits counts all digits; NUMERIC(p,s) restricts
                    # integral digits to p-s and can reject valid XML values.
                    if str(column.get('sql_type', '')).startswith('NUMERIC('):
                        column['sql_type'] = 'NUMERIC'
            model['constraint_enforcement'] = 'validated-source; PostgreSQL facet constraints not generated'
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
            'constraint_policy': policy,
            'xml_digest': hashlib.sha256(xml_content).hexdigest(), 'original_bytes': xml_content,
            'xml_document': canonical, 'rows': rows, 'links': links}


def business_view_plan(model, schema, definitions):
    """Explicit ODS-derived dimensions and aggregate facts with exact identities."""
    if not isinstance(definitions, list) or len(definitions) > 20:
        raise ValueError('business_views must be a list of at most 20 definitions')
    tables = {table['entity_id']: table for table in model['tables']}
    statements, names = [], set()
    for definition in definitions:
        if not isinstance(definition, dict) or not isinstance(definition.get('name'), str) or not definition['name'].strip():
            raise ValueError('Each business view requires a name')
        entity = tables.get(definition.get('entity_id'))
        if entity is None:
            raise ValueError('Business views require a known entity_id')
        view = sql_name('business:' + definition['name'])
        if view in names:
            raise ValueError('Duplicate business view name')
        names.add(view)
        source = f'"{schema}"."{entity["sql_name"]}"'
        if definition.get('kind') == 'dimension':
            if definition.get('grain') != 'business-key' or definition.get('history_policy') != 'immutable':
                raise ValueError('Dimensions require grain business-key and history_policy immutable')
            keys, attributes = definition.get('keys'), definition.get('attributes', [])
            if not isinstance(keys, list) or not 1 <= len(keys) <= 20 or not isinstance(attributes, list) or len(attributes) > 50:
                raise ValueError('Dimensions require 1-20 keys and at most 50 attributes')
            selected = [resolve_property(entity, ref) for ref in [*keys, *attributes]]
            fields = [column['sql_name'] for column in selected]
            if len(set(fields)) != len(fields):
                raise ValueError('Dimension keys and attributes must be distinct properties')
            key_fields = fields[:len(keys)]
            key_sql = ','.join(f'"{name}"' for name in key_fields)
            attribute_sql = ','.join(f'"{name}"' for name in fields[len(keys):])
            missing = ' OR '.join(f'"{name}" IS NULL' for name in key_fields)
            conflicts = (f'EXISTS (SELECT 1 FROM {source} GROUP BY {key_sql} '
                         f'HAVING COUNT(DISTINCT jsonb_build_array({attribute_sql})) > 1)') if attributes else 'FALSE'
            statements.append({'name': definition['name'], 'view': view, 'kind': 'dimension',
                'grain': 'business-key', 'history_policy': 'immutable', 'keys': key_fields,
                'attributes': fields[len(keys):], 'entity_id': entity['entity_id'],
                'output_columns': [{'name': field, 'source_property': field, 'role': 'dimension-key' if index < len(keys) else 'dimension-attribute'} for index, field in enumerate(fields)],
                'validation_sql': f'SELECT EXISTS (SELECT 1 FROM {source} WHERE {missing}) OR {conflicts} AS invalid',
                'sql': f'CREATE VIEW "{schema}"."{view}" AS SELECT DISTINCT ' + ','.join(f'"{name}"' for name in fields) + f' FROM {source}'})
            continue
        if definition.get('kind', 'aggregate') not in {'aggregate', 'fact'} or definition.get('grain') != 'entity-instance':
            raise ValueError('Aggregate facts require grain entity-instance')
        groups, measures = definition.get('group_by', []), definition.get('measures', [])
        if not isinstance(groups, list) or len(groups) > 50:
            raise ValueError('group_by must contain at most 50 known properties')
        group_columns = [resolve_property(entity, ref) for ref in groups]
        if len({column['sql_name'] for column in group_columns}) != len(group_columns):
            raise ValueError('group_by must contain distinct entity properties')
        if not isinstance(measures, list) or not measures or len(measures) > 30:
            raise ValueError('A business view requires 1-30 measures')
        expressions = [f'"{column["sql_name"]}" AS "{sql_name(ref)}"' for ref, column in zip(groups, group_columns)]
        output_columns = [{'name': sql_name(ref), 'source_property': column['sql_name'], 'role': 'group-key'} for ref, column in zip(groups, group_columns)]
        aliases = {sql_name(ref) for ref in groups}
        for measure in measures:
            if not isinstance(measure, dict):
                raise ValueError('Invalid business measure')
            name, aggregate, property_name = measure.get('name'), measure.get('aggregate'), measure.get('property')
            if not isinstance(name, str) or not name.strip() or sql_name(name) in aliases or aggregate not in {'count', 'sum', 'avg', 'min', 'max'}:
                raise ValueError('Measure names must be unique and aggregate must be count/sum/avg/min/max')
            aliases.add(sql_name(name))
            column = None if aggregate == 'count' and property_name is None else resolve_property(entity, property_name)
            if aggregate in {'sum', 'avg'} and not numeric_type(column['sql_type']):
                raise ValueError('sum/avg require a numeric property')
            if aggregate in {'min', 'max'} and not (numeric_type(column['sql_type']) or column['sql_type'] in {'TEXT', 'DATE', 'TIME', 'TIMESTAMPTZ'}):
                raise ValueError('min/max require an ordered numeric, text or temporal property')
            operand = '*' if column is None else f'"{column["sql_name"]}"'
            expressions.append(f'{aggregate.upper()}({operand}) AS "{sql_name(name)}"')
            output_columns.append({'name': sql_name(name), 'source_property': column['sql_name'] if column else None, 'role': 'measure', 'aggregate': aggregate})
        group_clause = ' GROUP BY ' + ','.join(f'"{column["sql_name"]}"' for column in group_columns) if groups else ''
        statements.append({'name': definition['name'], 'view': view, 'kind': definition.get('kind', 'aggregate'),
            'entity_id': entity['entity_id'], 'grain': 'entity-instance',
            'group_by': [column['sql_name'] for column in group_columns], 'output_columns': output_columns,
            'sql': f'CREATE VIEW "{schema}"."{view}" AS SELECT ' + ','.join(expressions) + f' FROM {source}' + group_clause})
    return statements


def flatten_xml(model, document):
    """Preserve namespace identity, repeated scalar values and child order."""
    # Dynamic XML typing needs a polymorphic relational mapping. Reject it
    # before extracting any row rather than silently losing derived fields.
    for node in document.iter():
        if node.get('{http://www.w3.org/2001/XMLSchema-instance}type') is not None:
            raise ValueError('XML xsi:type requires an explicit polymorphic projection; no data was loaded')
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
            if value == '' and column.get('source_kind') != 'attribute':
                fallback = column.get('default') if column.get('default') is not None else column.get('fixed')
                if fallback is not None:
                    value = fallback
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
                   'storage_layer': 'operational-data-store', 'constraint_policy': prepared.get('constraint_policy', 'strict'),
                   'execution_actor': payload.get('execution_actor'), 'loaded_at': datetime.now(timezone.utc).isoformat(),
                   'schema_digest': prepared['schema_digest'], 'xml_digest': prepared['xml_digest'],
                   'correlation_id': correlation_id, 'counts': {'entities': len(prepared['rows']), 'relationships': len(prepared['links']), 'source_documents': 1},
                   'business_views': [{key: value for key, value in view.items() if key not in {'sql', 'validation_sql'}} for view in prepared['business_views']],
                   'analytics_readiness': 'explicit-business-views-available' if prepared['business_views'] else 'structural-data-loaded; business-metrics-not-defined'}
        cursor.execute(sql.SQL('INSERT INTO {}.source_documents VALUES (%s,%s,XMLPARSE(DOCUMENT %s),%s)').format(sql.Identifier(prepared['schema'])),
                       (prepared['xml_digest'], prepared['original_bytes'], prepared['xml_document'], Jsonb(receipt)))
        identities = [None] * len(prepared['rows'])
        grouped = {}
        for index, (entity_id, values) in enumerate(prepared['rows']):
            grouped.setdefault(entity_id, []).append((index, values))
        for entity_id, entity_rows in grouped.items():
            table = tables[entity_id]
            # Bound parameters as well as row count for wide industrial tables.
            batch_size = max(1, min(500, 30000 // (len(table['columns']) + 2)))
            for start in range(0, len(entity_rows), batch_size):
                ensure_execution_allowed()
                batch = entity_rows[start:start + batch_size]
                cursor.execute("SELECT i, nextval(pg_get_serial_sequence(%s, 'instance_id')) FROM generate_series(0,%s) AS i ORDER BY i",
                               (f'"{prepared["schema"]}"."{table["sql_name"]}"', len(batch) - 1))
                allocated = dict(cursor.fetchall())
                if set(allocated) != set(range(len(batch))):
                    raise RuntimeError('Analytics identity allocation did not cover the load batch')
                values = []
                for ordinal, (index, row) in enumerate(batch):
                    identities[index] = allocated[ordinal]
                    values.extend([allocated[ordinal], *row, prepared['xml_digest']])
                columns = ['instance_id', *(column['sql_name'] for column in table['columns']), 'source_document_sha256']
                placeholders = sql.SQL('(') + sql.SQL(',').join(sql.Placeholder() for _ in columns) + sql.SQL(')')
                cursor.execute(sql.SQL('INSERT INTO {}.{} ({}) OVERRIDING SYSTEM VALUE VALUES {}').format(
                    sql.Identifier(prepared['schema']), sql.Identifier(table['sql_name']),
                    sql.SQL(',').join(sql.Identifier(name) for name in columns),
                    sql.SQL(',').join(placeholders for _ in batch)), values)
        link_batches = {}
        for entity_id, ordinal, parent, child, position in prepared['links']:
            relationship = tables[entity_id]['relationships'][ordinal]
            name = sql_name(entity_id + '/' + relationship['name'] + '/' + str(ordinal) + '/link')
            link_batches.setdefault(name, []).append((identities[parent], identities[child], position))
        for name, rows in link_batches.items():
            for start in range(0, len(rows), 500):
                ensure_execution_allowed()
                batch = rows[start:start + 500]
                cursor.execute(sql.SQL('INSERT INTO {}.{} (owner_id,child_id,position) VALUES {}').format(
                    sql.Identifier(prepared['schema']), sql.Identifier(name),
                    sql.SQL(',').join(sql.SQL('(%s,%s,%s)') for _ in batch)),
                    [value for row in batch for value in row])
        for view in prepared['business_views']:
            if view.get('validation_sql'):
                ensure_execution_allowed()
                cursor.execute(view['validation_sql'])
                result = cursor.fetchone()
                if not result or result[0]:
                    raise ValueError('Dimension keys are missing or map to conflicting attributes; use a reviewed history policy or a new projection')
        ensure_execution_allowed()
        cursor.execute('INSERT INTO depo_registry(namespace,key,value) VALUES (%s,%s,%s)', (registry.namespace, key, Jsonb(receipt)))
    return receipt
