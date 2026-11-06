"""Namespace-faithful identities for named source declarations."""
from urllib.parse import quote
X='{http://www.w3.org/2001/XMLSchema}'
SOURCE='{urn:pmem:conversion}'

def class_iri_map(roots):
    declarations=[]
    type_keys=set()
    for root in roots.values():
        for node in root:
            if node.tag not in {X+'complexType',X+'simpleType',X+'element'}:continue
            namespace=node.get(SOURCE+'sourceNamespace')
            name=node.get(SOURCE+'sourceName')
            if namespace is None or not name:continue
            if not namespace:continue  # no-namespace declarations retain generated ontology identity
            declarations.append((node,namespace,name))
            if node.tag != X+'element':type_keys.add((namespace,name))
    result={};reverse={}
    for node,namespace,name in declarations:
        local=('element/' if node.tag==X+'element' and (namespace,name) in type_keys else '')+quote(name,safe='._-')
        iri=namespace+('' if namespace.endswith(('#','/')) else '#')+local
        converted=node.get('name')
        if converted in result and result[converted]!=iri:
            raise ValueError('Conflicting converted class name across source namespaces')
        if iri in reverse and reverse[iri]!=converted:
            raise ValueError('Source declaration IRI collision')
        result[converted]=iri;reverse[iri]=converted
    return result
