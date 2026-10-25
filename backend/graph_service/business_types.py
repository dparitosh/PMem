"""Recognize canonical business instances by exact retained RDF types."""
import json
import re
CEIM_TYPES=frozenset({'Product','ProductRevision','Part','Assembly','Requirement','QualityMeasurement','Document','Change','Configuration','Test','Process','Resource','Feature','Characteristic','Datum','DatumReferenceFrame','PMIAnnotation','GeometryBody'})
CEIM_IRIS=tuple('https://depo.example.org/ceim/0.1/'+name for name in sorted(CEIM_TYPES))
def canonical_business_filter(alias):
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',alias):raise ValueError('Invalid Cypher variable')
    return f'({alias}:OntologyResource AND any(rdf_type IN coalesce({alias}.rdf_types,[]) WHERE rdf_type IN {json.dumps(CEIM_IRIS)}))'
def include_canonical_business_types(query):
    pattern=r'any\(label IN labels\(([A-Za-z_][A-Za-z0-9_]*)\) WHERE label IN \$instance_node_labels\)'
    return re.sub(pattern,lambda m:'('+m.group(0)+' OR '+canonical_business_filter(m.group(1))+')',query)

def is_canonical_business_instance(node):
    labels=set(node.get('labels') or [])
    if labels & {'StagedOntologyResource','RetainedOntologyIdentity','OntologyPublication'}:return False
    properties=node.get('properties') or {}
    types=properties.get('rdf_types') or []
    return isinstance(types,list) and bool(set(types).intersection(CEIM_IRIS))
