"""Negotiated read-only OSLC representations; unknown fields are extensions."""
import json
from urllib.parse import quote
from fastapi import HTTPException, Response
from rdflib import Graph, URIRef, BNode, Literal
from rdflib.namespace import RDF, RDFS, DCTERMS
from .media import negotiate

OSLC = 'http://open-services.net/ns/core#'
EXT = 'urn:depo:oslc:extension:'
PREFIXES = {'oslc': OSLC, 'rdf': str(RDF), 'rdfs': str(RDFS), 'dcterms': str(DCTERMS),
            'trs': 'http://open-services.net/ns/core/trs#',
            **{'oslc_' + domain: 'http://open-services.net/ns/' + domain + '#' for domain in ('rm', 'am', 'cm', 'qm')}}
CORE_FIELDS = {'resourceShape', 'propertyDefinition', 'describes', 'valueType', 'occurs',
               'readOnly', 'queryBase', 'nextPage', 'name', 'domain'}
FIELD_ALIASES = {'services': 'service', 'queryCapabilities': 'queryCapability',
                 'resourceShapes': 'resourceShape', 'serviceProviders': 'serviceProvider'}
LINK_FIELDS = {'uri', 'resourceShape', 'queryBase', 'propertyDefinition', 'serviceProvider',
               'nextPage', 'base', 'changeLog', 'describes', 'valueType', 'occurs', 'targetUri', 'domain', 'oslc:domain', 'resourceShapes'}


def expand(value):
    prefix, separator, local = str(value).partition(':')
    return PREFIXES[prefix] + local if separator and prefix in PREFIXES else str(value)


def rdf_graph(payload):
    graph = Graph()
    def visit(record):
        subject = URIRef(record['uri']) if record.get('uri') else BNode()
        for key, value in record.items():
            if key == 'uri' or value is None:
                continue
            if key == 'domainProperties':
                for property_name, property_value in value.items():
                    for item in property_value if isinstance(property_value, list) else [property_value]:
                        graph.add((subject, URIRef(expand(property_name)), URIRef(item) if property_name == 'oslc_rm:uses' else Literal(item)))
                continue
            shape_properties = key == 'properties' and record.get('type') == 'oslc:ResourceShape'
            predicate = RDF.type if key in {'type', 'rdf:type'} else RDFS.member if key == 'members' else DCTERMS.title if key == 'title' else RDFS.label if key == 'label' else URIRef(OSLC + 'property' if shape_properties else OSLC + FIELD_ALIASES[key] if key in FIELD_ALIASES else expand(key) if ':' in key else OSLC + key if key in CORE_FIELDS else EXT + quote(key, safe=''))
            for item in value if isinstance(value, list) else [value]:
                if isinstance(item, dict):
                    if key == 'members' and item.get('resource_uri'):
                        item = {**item, 'uri': item['resource_uri']}
                    if shape_properties:
                        item = dict(item)
                        definition = item.pop('uri', None)
                        if definition:
                            item.setdefault('propertyDefinition', definition)
                    obj = visit(item)
                elif key in LINK_FIELDS or key.startswith('oslc:') and key.endswith(('Provider', 'Shape')) or key in {'type', 'rdf:type'}:
                    iri = expand(item)
                    obj = URIRef(iri if ':' in iri else EXT + 'type:' + quote(iri, safe=''))
                else:
                    obj = Literal(item)
                graph.add((subject, predicate, obj))
        # Preserve the asserted predicate for actual resource links.
        for link in record.get('outgoingLinks', []):
            if link.get('predicate') and link.get('targetUri'):
                graph.add((subject, URIRef(link['predicate']), URIRef(link['targetUri'])))
        return subject
    visit(payload)
    return graph


def represent(payload, request):
    media = negotiate(request.headers.get('accept', 'application/json'))
    if media is None:
        raise HTTPException(406, 'No supported OSLC representation is acceptable')
    if media == 'application/json':
        body = json.dumps(payload, ensure_ascii=False, default=str).encode('utf-8')
    else:
        body = rdf_graph(payload).serialize(format={'text/turtle': 'turtle', 'application/rdf+xml': 'xml',
                                                    'application/ld+json': 'json-ld'}[media], encoding='utf-8')
    return Response(body, media_type=media, headers={'Vary': 'Accept', 'OSLC-Core-Version': '2.0',
                                                  'Cache-Control': 'private, no-cache'})
