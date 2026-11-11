"""Read metadata through its owning service, without a pipeline-local graph runtime."""
from urllib.parse import quote
import httpx
from backend.depo_platform.service_urls import service_url
from backend.depo_platform.network import service_bearer_headers
from backend.depo_platform.peer_http import peer_response

def read_metadata(asset_id=None,offset=0):
    root=service_url('SEMANTIC_REGISTRY_URL','http://127.0.0.1:8011/api/v1/metadata-registry').rstrip('/')
    endpoint=root+'/assets'+('/'+quote(asset_id,safe='') if asset_id else '')
    try:
        response=peer_response('GET',endpoint,headers=service_bearer_headers('GRAPH_READ_TOKEN',service_name='analytics metadata sources',endpoint=root),
            budget=10,response_limit=2*1024*1024,**({} if asset_id else {'params':{'limit':50,'offset':offset}}))
        if asset_id and response.status_code==404:return None
        response.raise_for_status();data=response.json()
        if not isinstance(data,dict) or (asset_id and data.get('asset_id')!=asset_id) or (not asset_id and not isinstance(data.get('assets'),list)):
            raise ValueError('Invalid metadata response')
        return data
    except (httpx.HTTPError,ValueError,OSError,TimeoutError) as exc:
        raise RuntimeError('Metadata Registry is unavailable; registered sources could not be verified') from exc
