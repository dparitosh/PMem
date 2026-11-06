"""Semantic mapper: rules to map source -> canonical -> application."""
from rdflib import Graph, RDF, RDFS
from rdflib.namespace import OWL
from typing import Dict, Any


class SemanticMapper:
    @staticmethod
    def align_source_to_canonical(source_g: Graph, canonical_g: Graph = None) -> Dict[str, Any]:
        if canonical_g is None:
            raise ValueError('A canonical graph is required for mapping proposals')
        candidates = {}
        for kind in (OWL.Class, OWL.ObjectProperty, OWL.DatatypeProperty):
            targets = {}
            for target in canonical_g.subjects(RDF.type, kind):
                for label in canonical_g.objects(target, RDFS.label):
                    normalized = str(label).strip().casefold()
                    if normalized:
                        targets.setdefault(normalized, set()).add(str(target))
            for source in source_g.subjects(RDF.type, kind):
                matches = set()
                for label in source_g.objects(source, RDFS.label):
                    matches.update(targets.get(str(label).strip().casefold(), set()))
                if matches:
                    candidates[str(source)] = {'targets': sorted(matches), 'status': 'requires_review',
                                               'reason': 'Exact label match within the same RDF type'}
        return candidates
