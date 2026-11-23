"""IIF-owned graph intent -> NEXUS REST; no app imports, DB access or LLM calls."""
import hashlib
import json
import math
import os
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl): return None


def selected_intent():
    path = os.environ.get('NEXUS_GRAPH_INTENT_FILE', '')
    if not path or not Path(path).is_absolute(): raise ValueError('Configure an absolute operator-owned graph intent file')
    with open(path, 'rb') as stream: raw = stream.read(16385)
    if len(raw)>16384: raise ValueError('Graph intent exceeds 16 KiB')
    def unique(pairs):
        out={}
        for key,value in pairs:
            if key in out: raise ValueError('Duplicate intent field')
            out[key]=value
        return out
    value=json.loads(raw,object_pairs_hook=unique)
    required={'ontology_id','publication_id','algorithm','predicates'}
    if not isinstance(value,dict) or not required<=value.keys() or value.keys()-required-{'node_id','top_n'}: raise ValueError('Invalid selected graph intent')
    for key,limit in (('ontology_id',128),('publication_id',128)):
        if not isinstance(value[key],str) or not 1<=len(value[key])<=limit: raise ValueError('Invalid scope identity')
    if value['algorithm'] not in ('pagerank','personalized-pagerank','node-similarity','traceability','triangle-count'): raise ValueError('Unsupported graph algorithm')
    predicates=value['predicates']
    if not isinstance(predicates,list) or not 1<=len(predicates)<=12 or any(not isinstance(p,str) or not 1<=len(p)<=800 for p in predicates) or len(set(predicates))!=len(predicates): raise ValueError('Invalid selected predicates')
    seed=value.get('node_id','')
    if value['algorithm'] in ('pagerank','triangle-count') and seed: raise ValueError('Global PageRank does not accept a seed')
    if not isinstance(seed,str) or len(seed)>256 or (value['algorithm'] not in ('pagerank','triangle-count') and not seed): raise ValueError('Select a seed record')
    top=value.get('top_n',10)
    if type(top) is not int or not 1<=top<=50: raise ValueError('Invalid result limit')
    return {**value,'node_id':seed,'top_n':top}


def eif_dt_compute_selected_graph():
    """Execute exactly the operator-selected intent. Takes no model arguments."""
    intent=selected_intent()
    base=os.environ.get('NEXUS_GRAPH_SERVICE_URL','http://127.0.0.1:8013/api/v1').rstrip('/')
    parsed=urlsplit(base)
    if parsed.username or parsed.password or parsed.query or parsed.fragment or not parsed.hostname or parsed.path.rstrip('/')!='/api/v1': raise ValueError('Configure the Graph service /api/v1 base URL')
    if parsed.scheme!='https' and not (parsed.scheme=='http' and parsed.hostname in {'127.0.0.1','localhost','::1'}): raise ValueError('Remote Graph service requires HTTPS')
    token=os.environ.get('NEXUS_GRAPH_READ_TOKEN','').strip()
    if not token: raise ValueError('Configure the scoped Graph read credential in IIF')
    request=Request(base+'/graph/computation',data=json.dumps(intent).encode(),method='POST',headers={'Content-Type':'application/json','Authorization':'Bearer '+token})
    try:
        with build_opener(NoRedirect).open(request,timeout=25) as response:
            raw=response.read(262145)
    except HTTPError as exc:
        raise RuntimeError('Graph computation rejected (HTTP '+str(exc.code)+'); inspect the service request log') from None
    except (URLError,TimeoutError): raise RuntimeError('Graph service unavailable; no result verified') from None
    if len(raw)>262144: raise ValueError('Graph result exceeds 256 KiB')
    result=json.loads(raw)
    if not isinstance(result,dict) or result.get('parameters')!=intent or result.get('ontology_id')!=intent['ontology_id'] or result.get('publication_id')!=intent['publication_id'] or result.get('advisory_only') is not True or result.get('approval_granted') is not False: raise ValueError('Graph response identity or authority mismatch')
    digest=result.get('projection_digest','')
    if not isinstance(digest,str) or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest): raise ValueError('Missing projection evidence digest')
    intent_digest=hashlib.sha256(json.dumps(intent,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return {'controller':'IIF','intent_digest':intent_digest,'evidence':result,'advisory_only':True}
