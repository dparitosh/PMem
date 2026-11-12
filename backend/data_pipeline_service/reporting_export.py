"""Freeze a consistent reporting snapshot for the existing product review flow."""
import json
from backend.artifact_store import ArtifactStore
from backend.depo_platform.execution_guard import ensure_execution_allowed
from . import reporting_store as store


def execute(runner,payload,*,correlation_id):
    identifier=payload.get('feed_id','');parts={};count=0;size=0;buffer=[];buffer_size=0
    artifacts=ArtifactStore()
    with store.registry()._connect() as db,db.transaction(),db.cursor() as c:
        c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
        feed=store.get(identifier,c);state=feed['state'];generation=state.get('active_generation')
        if feed['status']!='approved' or not generation:raise ValueError('Choose an initialized, approved reporting dataset')
        c.execute('SELECT count(*) FROM depo_reporting_resources WHERE feed_id=%s AND generation=%s',(identifier,generation))
        total=c.fetchone()[0]
        if not total:raise ValueError('No reporting records are available to export')
        if total>100000:raise ValueError('Partition this reporting selection before exporting more than 100000 resources')
        c.execute('SELECT payload FROM depo_reporting_resources WHERE feed_id=%s AND generation=%s ORDER BY resource_key',(identifier,generation))
        def flush():
            nonlocal buffer,buffer_size
            if not buffer:return
            part=artifacts.ingest_bytes(b''.join(buffer),filename=f'reporting-records-{len(parts)+1}.jsonl',kind='reporting-snapshot',media_type='application/x-ndjson',
                provenance={'feed_id':identifier,'generation':generation,'trs_after':state.get('trs_after'),'correlation_id':correlation_id})
            parts['records_'+str(len(parts)+1)]=part['artifact_id'];buffer=[];buffer_size=0
        while True:
            rows=c.fetchmany(500)
            if not rows:break
            for row in rows:
                ensure_execution_allowed();line=(json.dumps(row[0],ensure_ascii=False,separators=(',',':'))+'\n').encode()
                if len(line)>8*1024*1024:raise ValueError('Reporting record exceeds the snapshot partition limit')
                size+=len(line);count+=1
                if size>128*1024*1024:raise ValueError('Partition this reporting selection before exporting more than 128 MiB')
                if buffer_size+len(line)>8*1024*1024:flush()
                buffer.append(line);buffer_size+=len(line)
        flush()
    receipt={'feed_id':identifier,'generation':generation,'trs_after':state.get('trs_after'),'record_count':count,
             'source_definition':feed['definition'],'freshness_at_export':store.with_freshness(feed)['freshness'],
             'source_coverage':'Tracked events only; source publisher coverage remains partial.',
             'artifacts':parts,'database_views':['depo_reporting_entities','depo_reporting_property_values','depo_reporting_relationships']}
    return {'status':'completed','job_type':'trs-reporting-export','reporting_snapshot':receipt,'counts':{'records':count},
            'partition_artifacts':parts,'data_product_draft':{'contract':'reporting-snapshot-product-v1','name':feed['name']+' reporting snapshot',
             'product_kind':'pipeline-evidence','domain':'engineering-reporting','quality_status':'requires_review',
             'analytics_readiness':'Retained reporting records; business KPI definitions and publication require separate review',
             'sources':[{'feed_id':identifier,'generation':generation,'trs_after':state.get('trs_after')}],
             'artifacts':[{'artifact_id':artifact,'kind':'reporting-snapshot'} for artifact in parts.values()],
             'publication_requirements':['Approved semantic release','Data-product steward approval']}}
