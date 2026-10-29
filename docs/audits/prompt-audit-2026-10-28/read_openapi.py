import sys,json,asyncio,httpx
from pathlib import Path
root=Path(r'C:\Users\Admin\Documents\Codex\2026-10-18\in\pmem-publish');sys.path.insert(0,str(root))
from backend.agentic_service.catalog_loader import load_catalog
from backend.agentic_service.proposal_contracts import input_schema
out=Path(r'C:\Users\Admin\Documents\Codex\2026-10-18\in\outputs\prompt-audit-20261028')
ports=dict(qif=8010,ontology=8011,agentic=8012,graph=8013,ingestion=8014,oslc=8015,catalog=8016,data_products=8017,ceim=8018,data_pipeline=8019)
async def main():
    documents={};statuses={}
    async with httpx.AsyncClient(timeout=12,trust_env=False) as client:
        async def read(service,port):
            try:
                r=await client.get(f'http://127.0.0.1:{port}/openapi.json')
                statuses[service]=r.status_code
                if r.status_code==200:documents[service]=r.json()
            except httpx.HTTPError as e:statuses[service]=type(e).__name__
        await asyncio.gather(*(read(s,p) for s,p in ports.items()))
    tools=[]
    for tool in load_catalog()['tools']:
        if tool.get('transport')!='openapi':continue
        try:schema=input_schema(documents[tool['service']],tool);tools.append({'id':tool['id'],'schema':schema,'status':'resolved'})
        except Exception as e:tools.append({'id':tool['id'],'status':'unresolved','error':type(e).__name__})
    (out/'live-openapi-contracts.json').write_text(json.dumps({'services':statuses,'tools':tools},indent=2),encoding='utf-8')
    print(json.dumps({'services':statuses,'resolved':sum(t['status']=='resolved' for t in tools),'unresolved':[t['id'] for t in tools if t['status']!='resolved']}))
asyncio.run(main())