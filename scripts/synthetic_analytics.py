"""Standalone PostgreSQL schema-driven synthetic data and KPI test harness."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import random
import re
import uuid

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb


def inspect(db, schema):
    tables = {}
    rows = db.execute('''SELECT c.table_name,c.column_name,c.data_type,c.udt_name,
        c.character_maximum_length,c.numeric_precision,c.numeric_scale
        FROM information_schema.columns c JOIN information_schema.tables t
        USING(table_catalog,table_schema,table_name)
        WHERE c.table_schema=%s AND t.table_type='BASE TABLE'
        ORDER BY c.table_name,c.ordinal_position''', (schema,)).fetchall()
    for table, name, kind, udt, length, precision, scale in rows:
        tables.setdefault(table, {'columns': [], 'foreign_keys': []})['columns'].append(
            dict(name=name, kind=kind, udt=udt, length=length, precision=precision, scale=scale))
    keys = db.execute('''SELECT child.relname, pn.nspname, parent.relname,
        ARRAY(SELECT attname FROM unnest(k.conkey) WITH ORDINALITY x(n,i)
              JOIN pg_attribute a ON a.attrelid=k.conrelid AND a.attnum=x.n ORDER BY x.i),
        ARRAY(SELECT attname FROM unnest(k.confkey) WITH ORDINALITY x(n,i)
              JOIN pg_attribute a ON a.attrelid=k.confrelid AND a.attnum=x.n ORDER BY x.i)
        FROM pg_constraint k JOIN pg_class child ON child.oid=k.conrelid
        JOIN pg_namespace cn ON cn.oid=child.relnamespace
        JOIN pg_class parent ON parent.oid=k.confrelid
        JOIN pg_namespace pn ON pn.oid=parent.relnamespace
        WHERE k.contype='f' AND cn.nspname=%s ORDER BY child.relname,k.conname''', (schema,)).fetchall()
    for child, parent_schema, parent, columns, targets in keys:
        tables[child]['foreign_keys'].append(dict(parent_schema=parent_schema, parent=parent, columns=columns, targets=targets))
    if not tables:
        raise ValueError('No readable base tables in the selected source schema')
    return tables


def order_tables(tables, source):
    remaining = set(tables)
    ordered = []
    while remaining:
        ready = sorted(t for t in remaining if all(
            k['parent_schema'] == source and k['parent'] in ordered
            for k in tables[t]['foreign_keys']))
        if not ready:
            raise ValueError('Foreign keys contain a cycle, self-reference, external schema or unreadable parent; no data was created')
        ordered += ready
        remaining.difference_update(ready)
    return ordered


def value(column, index, rng):
    kind = column['kind']
    if kind in {'smallint', 'integer', 'bigint'}:
        return index + 1
    if kind in {'numeric', 'decimal', 'real', 'double precision'}:
        precision, scale = column['precision'], column['scale'] or 0
        if precision and precision - scale < 1:
            return round(rng.random() * .9, scale)
        upper = min(1000, 10 ** min(precision - scale, 6) - 1) if precision else 1000
        return round(rng.uniform(0, upper), min(scale, 6))
    if kind == 'boolean':
        return index % 2 == 0
    if kind in {'text', 'character varying', 'character'}:
        text = 'synthetic_' + str(index + 1)
        return text[:column['length']] if column['length'] else text
    if kind == 'uuid':
        return uuid.UUID(int=rng.getrandbits(128), version=4)
    if kind == 'date':
        return dt.date(2025, 1, 1) + dt.timedelta(days=index)
    if kind.startswith('timestamp'):
        return dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc) + dt.timedelta(hours=index)
    if kind.startswith('time'):
        return dt.time(index % 24, (index // 24) % 60)
    if kind in {'json', 'jsonb'}:
        return Jsonb({'synthetic': True, 'row': index + 1})
    if kind == 'bytea':
        return b'synthetic'
    if kind == 'xml':
        return '<Synthetic row="%d"/>' % (index + 1)
    raise ValueError('Unsupported column type: ' + kind + '. Supply a reviewed fixture instead.')


def generate(db, source, target, rows, seed, definitions):
    if not re.fullmatch(r'nexus_test_[a-z0-9_]{1,40}', target) or source == target:
        raise ValueError('Destination must be a new nexus_test_* schema distinct from the source')
    if not 1 <= rows <= 10000:
        raise ValueError('Rows per table must be between 1 and 10000')
    tables = inspect(db, source)
    if 'synthetic_test_receipt' in tables or any(name.startswith('synthetic_kpi_') for name in tables):
        raise ValueError('Source contains reserved synthetic output names')
    ordered = order_tables(tables, source)
    if len(tables) > 100:
        raise ValueError('Select a source schema with at most 100 tables')
    # Validate types before creating anything. All writes below are atomic.
    for table in tables.values():
        for column in table['columns']:
            value(column, 0, random.Random(seed))
    db.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(target)))
    db.execute(sql.SQL('COMMENT ON SCHEMA {} IS {}').format(sql.Identifier(target),
               sql.Literal('SYNTHETIC TEST DATA ONLY; seed=' + str(seed))))
    generated = {}
    rng = random.Random(seed)
    for name in ordered:
        # Deliberately exclude defaults, identities and source sequences.
        # Preserve check/not-null/unique constraints; FK constraints are remapped.
        db.execute(sql.SQL('CREATE TABLE {}.{} (LIKE {}.{} INCLUDING CONSTRAINTS INCLUDING INDEXES)').format(
            sql.Identifier(target), sql.Identifier(name), sql.Identifier(source), sql.Identifier(name)))
        columns = tables[name]['columns']
        records = []
        for index in range(rows):
            record = {c['name']: value(c, index, rng) for c in columns}
            for key in tables[name]['foreign_keys']:
                parent = generated[key['parent']][index % len(generated[key['parent']])]
                for child_column, parent_column in zip(key['columns'], key['targets']):
                    record[child_column] = parent[parent_column]
            records.append(record)
        statement = sql.SQL('INSERT INTO {}.{} ({}) VALUES ({})').format(
            sql.Identifier(target), sql.Identifier(name),
            sql.SQL(',').join(sql.Identifier(c['name']) for c in columns),
            sql.SQL(',').join(sql.Placeholder() for _ in columns))
        with db.cursor() as cursor:
            cursor.executemany(statement, [[r[c['name']] for c in columns] for r in records])
        generated[name] = records
        for i, key in enumerate(tables[name]['foreign_keys']):
            db.execute(sql.SQL('ALTER TABLE {}.{} ADD CONSTRAINT {} FOREIGN KEY ({}) REFERENCES {}.{} ({})').format(
                sql.Identifier(target), sql.Identifier(name), sql.Identifier('synthetic_fk_' + str(i)),
                sql.SQL(',').join(map(sql.Identifier, key['columns'])), sql.Identifier(target),
                sql.Identifier(key['parent']), sql.SQL(',').join(map(sql.Identifier, key['targets']))))
    report = {'synthetic': True, 'source_schema': source, 'test_schema': target, 'seed': seed, 'tables': {}, 'kpis': []}
    for name, table in tables.items():
        report['tables'][name] = {'rows': db.execute(sql.SQL('SELECT count(*) FROM {}.{}').format(
            sql.Identifier(target), sql.Identifier(name))).fetchone()[0], 'columns': {}}
        for column in table['columns']:
            if column['kind'] in {'json', 'xml'}:
                continue
            fields = db.execute(sql.SQL('SELECT count(*)-count({0}),count(DISTINCT {0}) FROM {1}.{2}').format(
                sql.Identifier(column['name']), sql.Identifier(target), sql.Identifier(name))).fetchone()
            report['tables'][name]['columns'][column['name']] = {'null_rows': fields[0], 'distinct_values': fields[1]}
            if column['kind'] in {'smallint','integer','bigint','numeric','decimal','real','double precision'}:
                stats = db.execute(sql.SQL('SELECT min({0}),max({0}),avg({0}),sum({0}) FROM {1}.{2}').format(
                    sql.Identifier(column['name']), sql.Identifier(target), sql.Identifier(name))).fetchone()
                report['tables'][name]['columns'][column['name']]['numeric_profile'] = dict(zip(('min','max','average','sum'), stats))
    if not definitions:
        # Observed inventory KPI, not an inferred engineering business metric.
        definitions = [{'name': name + ' synthetic row count', 'table': name, 'measure': table['columns'][0]['name'],
                        'aggregate': 'count', 'unit': 'records', 'dimensions': []} for name, table in tables.items()]
    for index, definition in enumerate(definitions):
        table, measure = definition['table'], definition['measure']
        operation = definition['aggregate']
        dimensions = definition.get('dimensions', [])
        allowed = {c['name']: c for c in tables.get(table, {}).get('columns', [])}
        if operation not in {'count', 'sum', 'avg', 'min', 'max'} or measure not in allowed or any(c not in allowed for c in dimensions):
            raise ValueError('Invalid KPI table, column, dimension or aggregate')
        if operation != 'count' and allowed[measure]['kind'] not in {'smallint','integer','bigint','numeric','decimal','real','double precision'}:
            raise ValueError('Numeric KPI requires a numeric measure')
        if not definition.get('name') or not definition.get('unit'):
            raise ValueError('Each KPI requires an explicit name and unit')
        groups = sql.SQL(',').join(map(sql.Identifier, dimensions))
        query = sql.SQL('SELECT {}{}{}({}) AS measure_value FROM {}.{}{}').format(
            groups, sql.SQL(',') if dimensions else sql.SQL(''), sql.SQL(operation), sql.Identifier(measure),
            sql.Identifier(target), sql.Identifier(table), sql.SQL(' GROUP BY {}').format(groups) if dimensions else sql.SQL(''))
        view = 'synthetic_kpi_' + str(index + 1)
        db.execute(sql.SQL('CREATE VIEW {}.{} AS {}').format(sql.Identifier(target), sql.Identifier(view), query))
        result = db.execute(sql.SQL('SELECT * FROM {}.{} ORDER BY {}').format(sql.Identifier(target),sql.Identifier(view),
            sql.SQL(',').join(sql.Identifier(c) for c in dimensions) if dimensions else sql.Identifier('measure_value'))).fetchall()
        report['kpis'].append({**definition, 'view': view, 'formula': operation + '(' + measure + ')', 'values': result})
    db.execute(sql.SQL('CREATE TABLE {}.synthetic_test_receipt (receipt jsonb NOT NULL)').format(sql.Identifier(target)))
    db.execute(sql.SQL('INSERT INTO {}.synthetic_test_receipt VALUES (%s)').format(sql.Identifier(target)), (Jsonb(json.loads(json.dumps(report, default=str))),))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path)
    parser.add_argument('--source-schema', required=True)
    parser.add_argument('--target-schema')
    parser.add_argument('--rows', type=int, default=25)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--kpis', type=Path, help='JSON list of explicit KPI definitions')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--execute', action='store_true', help='Without this, inspect metadata only')
    args = parser.parse_args()
    if args.env_file:
        from dotenv import load_dotenv
        load_dotenv(args.env_file, override=False)
    dsn = os.getenv('DEPO_TEST_DATABASE_URL') or os.getenv('DEPO_DATABASE_URL') or os.getenv('DATABASE_URL')
    if not dsn:
        parser.error('Set DEPO_TEST_DATABASE_URL, DEPO_DATABASE_URL or DATABASE_URL; do not pass credentials on the command line')
    definitions = json.loads(args.kpis.read_text(encoding='utf-8')) if args.kpis else []
    if not isinstance(definitions, list) or len(definitions) > 20:
        parser.error('KPI file must be a list with at most 20 definitions')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with psycopg.connect(dsn, connect_timeout=10, options='-c statement_timeout=30000 -c lock_timeout=5000') as db:
            if args.execute:
                if not args.target_schema:
                    parser.error('--execute requires --target-schema nexus_test_*')
                report = generate(db, args.source_schema, args.target_schema, args.rows, args.seed, definitions)
            else:
                db.execute('SET TRANSACTION READ ONLY')
                report = {'mode': 'metadata_only', 'schema': args.source_schema, 'tables': inspect(db, args.source_schema)}
        args.output.write_text(json.dumps(report, indent=2, default=str), encoding='utf-8')
        print('Synthetic test report written:', args.output)
    except (psycopg.Error, ValueError, KeyError, TypeError) as error:
        # Database errors can contain source values; never print connection strings.
        print('FAILED; database transaction rolled back. Error type:', type(error).__name__)
        if isinstance(error, psycopg.Error):
            print('SQLSTATE:', error.sqlstate, 'Constraint:', error.diag.constraint_name or 'not specified')
        elif isinstance(error, ValueError):
            print(str(error))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
