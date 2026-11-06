"""Reviewable structural analytics plans; no runtime DDL or graph publication."""
import re
from .xsd_relational_report import sql_name

def build_analytics_schema_plan(model, schema='analytics'):
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,62}', schema): raise ValueError('Invalid analytics schema identifier')
    blockers=list(model.get('ddl_blockers') or [])
    tables={table['entity_id']:table for table in model.get('tables',[])}
    statements=[]
    if not blockers:
        statements.append(f'CREATE SCHEMA "{schema}";')
        for entity in tables.values():
            columns=['"instance_id" BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY']
            for column in entity['columns']:
                if not column.get('sql_type'): raise ValueError('Unresolved SQL datatype')
                nullable='' if column.get('nullable', not column.get('required')) else ' NOT NULL'
                columns.append(f'"{column["sql_name"]}" {column["sql_type"]}{nullable}')
            statements.append(f'CREATE TABLE "{schema}"."{entity["sql_name"]}" ('+', '.join(columns)+');')
        for entity in tables.values():
            for index,relationship in enumerate(entity.get('relationships',[])):
                target=tables[relationship['target_entity_id']]
                name=sql_name(entity['entity_id']+'/'+relationship['name']+'/'+str(index)+'/link')
                uniqueness='' if relationship.get('repeating') else ', UNIQUE("owner_id")'
                statements.append(f'CREATE TABLE "{schema}"."{name}" ("owner_id" BIGINT NOT NULL REFERENCES "{schema}"."{entity["sql_name"]}"("instance_id"), "child_id" BIGINT NOT NULL REFERENCES "{schema}"."{target["sql_name"]}"("instance_id"), "position" BIGINT NOT NULL CHECK ("position" >= 0), PRIMARY KEY("owner_id","position"){uniqueness});')
    return {'contract':'xsd-analytics-schema-plan-v1','schema':schema,'execution_mode':'review-only',
        'ready_for_automatic_execution':False,'structural_mapping_complete':not blockers,
        'ddl_blockers':blockers,'sql':'\n'.join(statements),
        'entity_tables':[{'entity_id':t['entity_id'],'table':t['sql_name'],'grain':'one validated XML entity instance'} for t in tables.values()],
        'required_quality_checks':['compile XSD closure','validate XML instances against XSD','preserve particle order and group identity','reconcile source/load counts','check choice/cardinality and identity constraints'],
        'business_analytics':{'status':'requires_definition','facts':[],'dimensions':[],'metrics':[],
            'required_fields':['fact grain','dimension keys','measure expressions','units','aggregation rules','history policy']},
        'next_action':'Review the structural plan and define instance materialization/business metrics before migration and data-job approval. This plan does not update existing tables.'}
