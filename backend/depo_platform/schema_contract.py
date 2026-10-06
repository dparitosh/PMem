"""Read-only catalog verification of DEPO-owned SQL structures."""
import re
from backend.postgres_migrations import MIGRATIONS_DIR

CONSTRAINTS = {
 'depo_api_credentials_pkey': ('depo_api_credentials','PRIMARY KEY(profile)'),
 'depo_api_credential_events_pkey': ('depo_api_credential_events','PRIMARY KEY(event_id)'),
 'depo_schema_migrations_pkey': ('depo_schema_migrations','PRIMARY KEY(version)'),
 'depo_registry_pkey': ('depo_registry','PRIMARY KEY(namespace,key)'),
 'depo_registry_value_object': ('depo_registry',"CHECK(jsonb_typeof(value)='object')"),
 'depo_runtime_state_pkey': ('depo_runtime_state','PRIMARY KEY(kind,key)'),
 'depo_runtime_state_value_object': ('depo_runtime_state',"CHECK(jsonb_typeof(value)='object')"),
 'depo_chat_messages_pkey': ('depo_chat_messages','PRIMARY KEY(message_id)'),
 'depo_metadata_assets_pkey': ('depo_metadata_assets','PRIMARY KEY(asset_id)'),
 'depo_metadata_assets_revision_check': ('depo_metadata_assets','CHECK(revision>0)'),
 'depo_metadata_assets_value_check': ('depo_metadata_assets',"CHECK(jsonb_typeof(value)='object')"),
 'depo_metadata_events_pkey': ('depo_metadata_events','PRIMARY KEY(event_id)'),
 'depo_metadata_events_value_check': ('depo_metadata_events',"CHECK(jsonb_typeof(value)='object')"),
 'depo_metadata_events_revision_positive': ('depo_metadata_events','CHECK(revision>0)'),
 'depo_metadata_events_asset_id_revision_key': ('depo_metadata_events','UNIQUE(asset_id,revision)'),
 'depo_metadata_events_asset_id_fkey': ('depo_metadata_events','FOREIGN KEY(asset_id) REFERENCES depo_metadata_assets(asset_id)'),
 'depo_metadata_outbox_pkey': ('depo_metadata_outbox','PRIMARY KEY(event_id)'),
 'depo_metadata_outbox_event_id_fkey': ('depo_metadata_outbox','FOREIGN KEY(event_id) REFERENCES depo_metadata_events(event_id)'),
 'depo_metadata_outbox_status_check': ('depo_metadata_outbox',"CHECK(status=ANY(ARRAY['pending','published']))"),
}
INDEXES = {
 'idx_depo_chat_messages': 'ON depo_chat_messages(session_id,message_id)',
 'idx_depo_rate_limits': 'ON depo_rate_limits(client_key,created_at)',
 'idx_metadata_pending': "ON depo_metadata_outbox(created_at) WHERE status='pending'",
 'idx_depo_pipeline_runnable': "ON depo_registry(updated_at,key) WHERE namespace='data_job_runs' AND (value->>'status')=ANY(ARRAY['queued','running'])",
 'idx_depo_registry_recent': 'ON depo_registry(namespace,updated_at DESC,key)',
 'idx_depo_product_published': "ON depo_registry(COALESCE(value->>'published_at','') DESC,key DESC) WHERE namespace='data_products'",
 'idx_depo_job_started': "ON depo_registry(COALESCE(value->>'started_at','') DESC,key DESC) WHERE namespace='data_job_runs'",
 'idx_depo_catalog_updated': "ON depo_registry(COALESCE(value->>'updated_at','') DESC,key DESC) WHERE namespace='catalog_products' AND right(key,7)<>':latest'",
}

def normalize(sql, schema):
    sql = sql.lower().replace('"', '').replace(schema.lower()+'.', '').replace('depo_registry.', '')
    sql = re.sub(r'else\s+null::numeric', '', sql)
    sql = sql.replace('::text[]','').replace('::text','').replace('using btree','')
    return re.sub(r'[\s();]+', '', sql)

def verify_structure(cursor, schema, columns):
    cursor.execute("SELECT table_name,column_name,is_nullable,column_default FROM information_schema.columns WHERE table_schema=%s", (schema,))
    attributes = {(table,column):(nullable,default) for table,column,nullable,default in cursor.fetchall()}
    defaults = {('depo_schema_migrations','applied_at'):'now()', ('depo_registry','updated_at'):'now()',
                ('depo_metadata_assets','updated_at'):'now()', ('depo_metadata_events','created_at'):'now()',
                ('depo_metadata_outbox','created_at'):'now()', ('depo_metadata_outbox','status'):"'pending'::text"}
    for table, names in columns.items():
        if table == 'depo_ontology_analytics': continue
        for column in names:
            nullable, default = attributes.get((table,column), (None,None))
            if (table, column) == ('depo_api_credentials', 'expires_at'):
                if nullable != 'YES':
                    raise RuntimeError('Credential expiry must allow keys without expiration')
                continue
            if column != 'checksum' and nullable != 'NO':
                raise RuntimeError(f'Required column must be NOT NULL: {table}.{column}')
            if (table,column) in defaults and normalize(str(default),schema) != normalize(defaults[(table,column)],schema):
                raise RuntimeError(f'Invalid column default: {table}.{column}')
    cursor.execute("SELECT pg_get_serial_sequence(%s, 'message_id')", (f'"{schema}".depo_chat_messages',))
    row = cursor.fetchone()
    default = attributes.get(('depo_chat_messages','message_id'), (None,None))[1]
    if not row or not row[0] or normalize(str(default),schema) != normalize(f"nextval('{row[0]}'::regclass)",schema):
        raise RuntimeError('depo_chat_messages.message_id must use its owned sequence')
    cursor.execute("SELECT t.relname,c.conname,pg_get_constraintdef(c.oid),c.convalidated,fn.nspname FROM pg_constraint c JOIN pg_class t ON t.oid=c.conrelid JOIN pg_namespace n ON n.oid=t.relnamespace LEFT JOIN pg_class ft ON ft.oid=c.confrelid LEFT JOIN pg_namespace fn ON fn.oid=ft.relnamespace WHERE n.nspname=%s", (schema,))
    actual = {name:(table,definition,valid,foreign_schema) for table,name,definition,valid,foreign_schema in cursor.fetchall()}
    for name, (table,definition) in CONSTRAINTS.items():
        found = actual.get(name)
        if not found or found[0] != table or not found[2] or (found[3] and found[3] != schema) or normalize(found[1],schema) != normalize(definition,schema):
            raise RuntimeError(f'Invalid PostgreSQL constraint definition or validation: {name}')
    cursor.execute("SELECT ic.relname,pg_get_indexdef(i.indexrelid),i.indisvalid,i.indisready FROM pg_index i JOIN pg_class ic ON ic.oid=i.indexrelid JOIN pg_namespace n ON n.oid=ic.relnamespace WHERE n.nspname=%s", (schema,))
    indexes = {name:(definition,valid,ready) for name,definition,valid,ready in cursor.fetchall()}
    for name, suffix in INDEXES.items():
        found = indexes.get(name)
        expected = f'CREATE INDEX {name} {suffix}'
        if not found or not found[1] or not found[2] or normalize(found[0],schema) != normalize(expected,schema):
            raise RuntimeError(f'Invalid PostgreSQL index definition or validity: {name}')
    cursor.execute("SELECT c.relname,c.relkind FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=%s", (schema,))
    kinds = dict(cursor.fetchall())
    for table in columns:
        if kinds.get(table) != ('v' if table == 'depo_ontology_analytics' else 'r'):
            raise RuntimeError(f'Invalid PostgreSQL relation kind: {table}')
    cursor.execute("SELECT pg_get_viewdef(c.oid) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=%s AND c.relname='depo_ontology_analytics'", (schema,))
    row = cursor.fetchone()
    expected = (MIGRATIONS_DIR/'004_ontology_analytics_view.sql').read_text(encoding='utf-8').split('AS\n',1)[1]
    if not row or normalize(row[0],schema) != normalize(expected,schema):
        raise RuntimeError('Invalid depo_ontology_analytics view definition')
