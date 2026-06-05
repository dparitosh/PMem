"""Generate application ontology from canonical ontology.

The application ontology maps canonical concepts to business concepts.
"""
from rdflib import Graph, Namespace, RDF, RDFS, URIRef, Literal
from rdflib.namespace import OWL
from typing import Dict, Any

APP = Namespace('http://example.org/application/')


class ApplicationOntology:
    @staticmethod
    def from_canonical_graph(can_g: Graph, domain: str = 'default') -> Graph:
        g = Graph()
        g.bind('app', APP)
        g.bind('owl', OWL)

        # Minimal transform: copy classes and add domain tag
        for s, p, o in can_g.triples((None, RDF.type, OWL.Class)):
            new_c = URIRef(APP[s.split('/')[-1]])
            g.add((new_c, RDF.type, OWL.Class))
            for _, lp, lo in can_g.triples((s, RDFS.label, None)):
                g.add((new_c, RDFS.label, lo))
            g.add((new_c, APP.domain, Literal(domain)))

        return g
