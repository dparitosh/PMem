"""Reviewed, bounded reads through Semantica. Never dispatch caller tool names."""
import dataclasses
import json
import re
import time
from pathlib import Path
from backend.depo_platform.semantica_ingestors import load_ingestor
from .connector_sources import MAX_BYTES, MAX_RECORDS


class ReadOnlyMailbox:
    def __init__(self, client): self.client=client
    def __getattr__(self,name): return getattr(self.client,name)
    def select(self,mailbox,*args,**kwargs): return self.client.select(mailbox,readonly=True)
    def fetch(self,message,parts): return self.client.fetch(message,parts.replace('RFC822','BODY.PEEK[]'))


def plain(value, depth=0):
    if depth>15: raise ValueError('Connector record nesting exceeds supported depth')
    if dataclasses.is_dataclass(value): value=dataclasses.asdict(value)
    if hasattr(value,'to_dict'): value=value.to_dict(orient='records')
    if isinstance(value,dict):
        return {str(k):plain(v,depth+1) for k,v in value.items() if not re.search(r'password|secret|authorization|access.?token|connection.?(?:string|url)|dsn|api.?key|private.?key',str(k),re.I)}
    if isinstance(value,(list,tuple)):
        if len(value)>MAX_RECORDS: raise ValueError('Connector returned too many records')
        return [plain(v,depth+1) for v in value]
    if isinstance(value,bytes): return value.decode('utf-8')
    if value is None or isinstance(value,(str,int,float,bool)): return value
    return str(value)


def rows(value):
    value=plain(value)
    # SDK envelopes differ; retain one resource as a record when there is no
    # documented row collection. Never turn metadata into business assertions.
    if isinstance(value,dict):
        for key in ('data','records','items','messages','emails','entries','code_files'):
            if isinstance(value.get(key),list): value=value[key];break
    result=value if isinstance(value,list) else [value]
    result=[r if isinstance(r,dict) else {'value':r} for r in result]
    if len(result)>MAX_RECORDS or len(json.dumps(result,ensure_ascii=False,allow_nan=False).encode())>MAX_BYTES:
        raise ValueError('Connector output exceeds acquisition limits')
    return {'records':result,'record_count':len(result),'semantic_validation':'not_assessed'}


def local_file(resource,settings):
    root=Path(settings['root']).resolve(strict=True)
    target=(root/resource).resolve(strict=True)
    if root not in target.parents or not target.is_file() or target.stat().st_size>MAX_BYTES:
        raise ValueError('Select a bounded file inside the configured source root')
    return target


def acquire(kind,resource,settings):
    cls=load_ingestor(kind)
    client=None
    try:
        if kind in {'Parquet','Arrow'}:
            client=cls();result=client.ingest_file(local_file(resource,settings),limit=MAX_RECORDS,include_data=True)
        elif kind in {'Web','Feed','PublicAPI'}:
            from .rest_sources import endpoint_url
            endpoint_url(resource)
            client=cls(config={'timeout':10,'max_retries':0,'allow_private_ips':False})
            if kind=='Web': result=client.ingest_url(resource,timeout=10)
            elif kind=='Feed': result=client.ingest_feed(resource,timeout=10)
            else: result=client.ingest_public_api(resource,method='GET',require_public=True)
        elif kind=='DB':
            if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',resource): raise ValueError('Choose one configured table identifier')
            client=cls(config={'fail_fast':True});database=client.ingest_database(settings['connection_string'],include_tables=[resource],max_rows_per_table=MAX_RECORDS);result=database['tables'][resource]['rows']
        elif kind in {'Databricks','Snowflake'}:
            if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',resource): raise ValueError('Choose one configured table identifier')
            allowed={'host','token','http_path','catalog','schema','client_id','client_secret'} if kind=='Databricks' else {'account','user','password','warehouse','database','schema','role','authenticator','token'}
            if set(settings)-allowed: raise ValueError('Unsupported warehouse connection fields')
            client=cls(**settings);result=client.ingest_table(resource,limit=MAX_RECORDS)
        elif kind=='Email':
            client=cls();client.connect_imap(settings['server'],port=993,username=settings['username'],password=settings['password'])
            client.imap_client=ReadOnlyMailbox(client.imap_client)
            result=client.ingest_mailbox(resource,protocol='imap',max_emails=MAX_RECORDS)
        elif kind=='MCP':
            from .rest_sources import endpoint_url
            endpoint_url(settings['url'])
            client=cls();client.connect('configured-source',url=settings['url'],headers=settings.get('headers',{}))
            result=client.read_resource('configured-source',resource)
        elif kind=='Repo':
            from .rest_sources import endpoint_url
            endpoint_url(resource)
            client=cls();result=client.ingest_repository(resource,depth=1,single_branch=True,no_tags=True,include_history=False,include_extensions=['md','txt','json','yaml','yml','py','js','java','xml','ttl'])
        elif kind=='CloudStorage':
            provider=settings.get('provider')
            if provider not in {'s3','gcs','azure'}: raise ValueError('Choose S3, GCS or Azure storage')
            client=cls(provider,**settings.get('credentials',{}))
            content=client.download_object(settings['bucket'],resource)
            if len(content)>MAX_BYTES: raise ValueError('Cloud object exceeds acquisition limit')
            text=content.decode('utf-8')
            result=json.loads(text) if resource.lower().endswith('.json') else {'name':resource,'content':text}
        elif kind=='Stream':
            # Bounded Kafka snapshot, never an unbounded browser-owned consumer.
            # No group offsets are committed and no topic mutations are exposed.
            client=cls();processor=client.ingest_kafka(resource,settings['bootstrap_servers'],consumer_config={
                'enable_auto_commit':False,'group_id':None,'auto_offset_reset':'earliest',
                'request_timeout_ms':10000,'api_version_auto_timeout_ms':5000,
                **{k:v for k,v in settings.get('consumer_config',{}).items() if k in {'security_protocol','sasl_mechanism','sasl_plain_username','sasl_plain_password','ssl_cafile'}}})
            result=[];deadline=time.monotonic()+10
            try:
                while time.monotonic()<deadline and len(result)<MAX_RECORDS:
                    batch=processor.consumer.poll(timeout_ms=500,max_records=MAX_RECORDS-len(result))
                    for messages in batch.values(): result.extend(m.value for m in messages)
            finally: processor.consumer.close()
        else: raise ValueError('Unsupported reviewed connector')
        return rows(result)
    finally:
        # Close known resource owners even on validation/serialization failure.
        for owner in (getattr(client,'connector',None),client):
            for method in ('disconnect','close','cleanup'):
                close=getattr(owner,method,None)
                if callable(close):
                    try: close()
                    except Exception: pass
                    break
