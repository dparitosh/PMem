"""Explicit TRS RDF vocabulary; extension counters are not standard event terms."""
from urllib.parse import quote
from rdflib import URIRef, Literal, RDF, Namespace

TRS=Namespace('http://open-services.net/ns/core/trs#')
OSLC=Namespace('http://open-services.net/ns/core#')
RDFS=Namespace('http://www.w3.org/2000/01/rdf-schema#')


def event_uri(root, identifier):
    return root.split('/oslc/trs',1)[0]+'/oslc/trs/changelog#event-'+quote(str(identifier),safe='')


def add_trs(graph,payload):
    graph.bind('trs',TRS);graph.bind('oslc',OSLC)
    subject=URIRef(payload['uri']);kind=payload['type'].split(':',1)[1]
    graph.add((subject,RDF.type,TRS[kind]))
    if kind=='TrackedResourceSet':
        for key in ('base','changeLog'):
            graph.add((subject,TRS[key],URIRef(payload[key])))
    elif kind=='Base':
        for member in payload.get('members',[]):
            graph.add((subject,RDFS.member,URIRef(member.get('resource_uri') or member['uri'])))
        if payload.get('cutoff_event'):
            graph.add((subject,TRS.cutoffEvent,URIRef(event_uri(payload['uri'],payload['cutoff_event']))))
        if payload.get('nextPage'):graph.add((subject,OSLC.nextPage,URIRef(payload['nextPage'])))
    elif kind=='ChangeLog':
        for event in sorted(payload.get('events',[]),key=lambda item:item['order'],reverse=True):
            node=URIRef(event_uri(payload['uri'],event['event_id']))
            graph.add((subject,TRS.change,node))
            graph.add((node,RDF.type,TRS[event['event_type']]))
            graph.add((node,TRS.changed,URIRef(event['resource_uri'])))
            graph.add((node,TRS.order,Literal(event['order'])))
    return graph
