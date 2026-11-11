"""Compatibility bridge: old callers share the current engineering analysis."""
from fastapi import HTTPException
from backend.graph_service.recommendation_engine import RecommendationEngine, EXCLUDED


class QueryPublisher:
    def __init__(self, graph):
        self.graph = graph

    def _session_rows(self, query, _timeout_seconds=None, **parameters):
        return self.graph.query(query, params=parameters, timeout=_timeout_seconds) or []


def analyse(graph, mode, name, scope=None, node_id=None, top_n=10):
    publisher = QueryPublisher(graph)
    engine = RecommendationEngine(publisher)
    engine.scope(scope)
    scope = scope or {}
    identity = node_id or scope.get('node_id') or scope.get('element_id')
    if not identity:
        rows = engine.query(
            '/* recommendation-compat-source */ MATCH (n) '
            'WHERE none(label IN labels(n) WHERE label IN $excluded) '
            "AND toLower(coalesce(n.name,n.label,n.title,'')) CONTAINS toLower($name) "
            "AND ($scope='' OR n.ontology_id=$scope OR n.source_ontology=$scope) "
            "AND ($prefix='' OR n.prefix=$prefix OR n.ontology_prefix=$prefix) "
            'RETURN elementId(n) AS id, coalesce(n.name,n.label,n.title) AS name '
            'ORDER BY id LIMIT 26', name=name, excluded=EXCLUDED, **engine.scope(scope))
        if not rows:
            return {'message': 'No matching business record was found.', 'similar_parts': [],
                    'impacted_parts': [], 'assembly_impact': [], 'impacted_requirements': [],
                    'process_impacts': [], 'realization_chain': []}
        exact = [row for row in rows if row['name'].casefold() == name.casefold()]
        if len(rows) >= 26 or len(exact) > 1 or (not exact and len(rows) > 1):
            raise HTTPException(409, 'Select the exact business object identity and scope')
        identity = (exact or rows)[0]['id']
    return engine.similar(identity, scope, top_n) if mode == 'similar' else engine.impact(identity, scope)
