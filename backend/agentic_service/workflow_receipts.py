"""Verify durable downstream receipts without repeating a workflow mutation."""
from urllib.parse import quote


def verify_product_receipt(inputs, receipt):
    if not isinstance(receipt,dict) or not inputs.get('idempotency_key'):
        raise ValueError('No verifiable publication request identity is retained')
    if any(receipt.get(key) != inputs.get(key) for key in ('product_id','version','idempotency_key')):
        raise ValueError('Downstream receipt belongs to a different publication')
    if not isinstance(inputs.get('artifacts'),list) or not isinstance(receipt.get('artifacts'),list):
        raise ValueError('Publication receipt has an invalid artifact collection')
    expected = {item['artifact_id'] for item in inputs.get('artifacts',[]) if isinstance(item,dict) and item.get('artifact_id')}
    actual = {item['artifact_id'] for item in receipt.get('artifacts',[]) if isinstance(item,dict) and item.get('artifact_id')}
    if not expected or expected != actual or not receipt.get('publication_digest'):
        raise ValueError('Downstream receipt does not match the retained artifacts')
    return receipt


async def lookup(record, request):
    from fastapi import HTTPException
    from . import router as routes
    pending = record.get('pending_step') or {}
    inputs = pending.get('inputs') or {}
    tool = pending.get('tool_id')
    if tool == 'data.product.publish':
        import httpx
        from .transport_auth import downstream_headers
        product = str(inputs.get('product_id',''))+':'+str(inputs.get('version',''))
        endpoint = routes._base('data_products')+'/data-products/'+quote(product,safe='')
        async with httpx.AsyncClient(timeout=15,trust_env=False) as client:
            response = await routes._bounded_tool_request(client,'GET',endpoint,headers=downstream_headers(request,endpoint,graph_read=True))
        return verify_product_receipt(inputs,response.json())
    if tool in {'bridge.mapping.publish', 'bridge.mapping.publish_automatic'}:
        from .bridge_router import jobs
        preview = await routes._agent_io(jobs.get,inputs.get('preview_id',''))
        approved = inputs.get('approved_candidate_ids',[])
        if tool == 'bridge.mapping.publish_automatic':
            decision = await routes._agent_io(jobs.evaluate_policy, inputs['preview_id'])
            approved = decision['accepted_ids']
        return await routes._agent_io(jobs.reconcile_receipt,preview['publication_job_id'],approved)
    if tool in {'ontology.merge.apply', 'ontology.merge.apply_automatic'}:
        import httpx
        from .transport_auth import downstream_headers
        identifier = inputs.get('preview_id')
        if not isinstance(identifier, str) or not identifier:
            raise ValueError('No saved merge preview identity is retained')
        endpoint = routes._base('ontology')+'/ontologies/merges/'+quote(identifier,safe='')+'/receipt'
        async with httpx.AsyncClient(timeout=15,trust_env=False) as client:
            response = await routes._bounded_tool_request(client,'GET',endpoint,headers=downstream_headers(request,endpoint,graph_read=True))
        receipt = response.json()
        if not isinstance(receipt,dict) or receipt.get('preview_id') != identifier or receipt.get('status') != 'merged' or not (receipt.get('ontology') or {}).get('ontology_id'):
            raise ValueError('Invalid retained merge receipt')
        if inputs.get('publish') is True:
            ontology_id = receipt['ontology']['ontology_id']
            publication_endpoint = routes._base('ontology')+'/ontologies/'+quote(ontology_id,safe='')+'/publication'
            async with httpx.AsyncClient(timeout=15,trust_env=False) as client:
                response = await routes._bounded_tool_request(client,'GET',publication_endpoint,headers=downstream_headers(request,publication_endpoint,graph_read=True))
            publication = response.json()
            if not isinstance(publication, dict) or publication.get('status') != 'published' or publication.get('ontology_id') != ontology_id:
                raise ValueError('Merged artifact exists but Neo4j publication is not verified; retry the reviewed merge')
            return {**receipt, 'publication_status': 'published', 'publication': publication}
        return receipt
    raise HTTPException(409,'This tool has no verifiable receipt adapter; use explicit downstream evidence')


def compensation_plan(record):
    if record.get('status') in {'running','queued'} or record.get('pending_step') or record.get('reconciliation_required'):
        raise ValueError('Stop execution and reconcile uncertain writes before compensation')
    actions, unsupported = [], []
    for trace in reversed(record.get('traces',[])):
        if trace.get('status') != 'completed': continue
        result = trace.get('result') or {}
        if trace.get('tool_id') == 'data.product.publish' and result.get('product_id') and result.get('version'):
            actions.append({'sequence':trace['sequence'],'tool_id':'data.product.revoke',
                            'product_version':f"{result['product_id']}:{result['version']}",
                            'effect':'Revoke lifecycle and catalog registration; retain original artifacts and history'})
        elif (record.get('workflow_definition',{}).get('steps') or []):
            steps = record['workflow_definition']['steps']
            index = trace.get('sequence',0)-1
            if 0 <= index < len(steps) and steps[index].get('tool',{}).get('mutates'):
                unsupported.append({'sequence':trace['sequence'],'tool_id':trace['tool_id'],'reason':'No approved reversible service operation is defined'})
    return {'actions':actions,'unsupported':unsupported,'requires_approval':True,'automatic_rollback':False}
