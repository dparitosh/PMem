"""Idempotent display-metadata upgrade. Apply only with application services stopped."""
import argparse
import json
from pathlib import Path
from dotenv import load_dotenv


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--env-file',default=str(Path(__file__).resolve().parents[2]/'.env.local'))
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    load_dotenv(args.env_file,override=True)
    root=Path(__file__).resolve().parents[2]
    if args.apply and any((root/'logs/windows-services').glob('*.pid')):
        raise SystemExit('Stop application services with manage-depo before applying display metadata. No records changed.')
    from backend.mesh_store import PostgresRegistry
    from backend.oslc_service.change_control import SOURCES
    from backend.depo_platform.resource_identity import ensure, identify
    from backend.depo_platform.run_labels import source_name
    counts={'scanned':0,'eligible':0,'updated':0,'applied':args.apply}
    for source,(namespace,*_) in SOURCES.items():
        if source in {'products','learning'}:continue
        store=PostgresRegistry(namespace);offset=0
        while True:
            total,keys=store.page_keys(offset,100)
            for key in keys:
                record=store.get(key)
                if not isinstance(record,dict):continue
                counts['scanned']+=1
                change=record if source=='releases' and record.get('kind')=='release-change' else record.get('change_request')
                name=source_name(record) if source=='pipeline' else ''
                is_run=source=='pipeline' and bool(record.get('run_id'))
                if not isinstance(change,dict) and not name and not is_run:continue
                counts['eligible']+=1
                if args.apply:
                    before=json.dumps(record,sort_keys=True)
                    if isinstance(change,dict):ensure(change,source,str(record.get('request_id') or record.get('run_id') or record.get('preview_id') or record.get('job_id') or key))
                    if name:record['source_name']=name
                    if is_run:
                        identity=identify('RUN','data-pipeline',record['run_id'],name=name or record.get('job_id',''),links={'workflow_id':record.get('job_id')})
                        record.update(object_uuid=identity['object_id'],run_number=identity['number'])
                    if before!=json.dumps(record,sort_keys=True):store.put(key,record);counts['updated']+=1
            offset+=len(keys)
            if not keys or offset>=total:break
    # Definitions and source registrations retain their existing keys and URLs.
    for namespace,kind,source,id_field,uuid_field,number_field in (
        ('data_job_definitions','WF','data-pipeline','job_id','workflow_uuid','workflow_number'),
        ('rest_sources','DS','rest','source_id','source_uuid','source_number'),
        ('connector_sources','DS','connector','source_id','source_uuid','source_number'),
    ):
        store=PostgresRegistry(namespace);offset=0
        while True:
            total,keys=store.page_keys(offset,100)
            for key in keys:
                record=store.get(key)
                if not isinstance(record,dict):continue
                counts['scanned']+=1
                if not record.get(id_field):continue
                counts['eligible']+=1
                if args.apply:
                    identity=identify(kind,source,record[id_field],name=record.get('name',''))
                    if record.get(uuid_field)!=identity['object_id'] or record.get(number_field)!=identity['number']:
                        record.update({uuid_field:identity['object_id'],number_field:identity['number']})
                        store.put(key,record);counts['updated']+=1
            offset+=len(keys)
            if not keys or offset>=total:break
    # Legacy event labels are descriptive metadata only. Never infer CR/CO links.
    from backend.artifact_store import ArtifactStore
    events=PostgresRegistry('speed_path_reconciliations');offset=0
    while True:
        total,keys=events.page_keys(offset,100)
        for key in keys:
            record=events.get(key)
            if not isinstance(record,dict) or record.get('name') or not record.get('partition_artifact_id'):continue
            counts['scanned']+=1
            try:
                _,path=ArtifactStore().resolve(record['partition_artifact_id'])
                if path.stat().st_size>8*1024*1024:continue
                batch=json.loads(path.read_text(encoding='utf-8'))
                names=[row.get('properties',{}).get('name') for row in batch.get('entities',[]) if isinstance(row,dict) and isinstance(row.get('properties'),dict) and isinstance(row['properties'].get('name'),str)]
                if not names:continue
                name=names[0][:160]+(' + '+str(len(batch['entities'])-1)+' records' if len(batch['entities'])>1 else '')
            except (ValueError,OSError,KeyError,TypeError):continue
            counts['eligible']+=1
            if args.apply:
                if events.compare_and_put(key,record,{**record,'name':name}):counts['updated']+=1
        offset+=len(keys)
        if not keys or offset>=total:break
    print(json.dumps(counts))

if __name__=='__main__':main()
