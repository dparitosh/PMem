"""Allowlisted, bounded descriptions for search; no arbitrary node properties."""
import json

PREDICATES = {
    'http://www.w3.org/2004/02/skos/core#definition':'definition',
    'http://www.w3.org/2000/01/rdf-schema#comment':'comment',
    'http://purl.org/dc/terms/description':'description',
    'http://www.w3.org/2004/02/skos/core#prefLabel':'prefLabel',
    'http://www.w3.org/2004/02/skos/core#altLabel':'altLabel',
}


def search_properties(node):
    output={}
    if isinstance(node.get('description'),str):output['description']=node['description'][:1000]
    raw=node.get('rdf_properties')
    if isinstance(raw,str) and len(raw)<=16384:
        try:annotations=json.loads(raw)
        except ValueError:annotations={}
        if isinstance(annotations,dict):
            for predicate,name in PREDICATES.items():
                values=annotations.get(predicate)
                if isinstance(values,list):
                    text=[item['value'][:1000] for item in values[:8] if isinstance(item,dict) and isinstance(item.get('value'),str)]
                    if text:output[name]='; '.join(text)[:1000]
    for name in ('prefix','updated_at','publication_revision'):
        if isinstance(node.get(name),str):output[name]=node[name][:256]
    return output
