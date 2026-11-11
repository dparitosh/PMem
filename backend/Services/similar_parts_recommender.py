"""Compatibility API for the shared engineering recommendation engine."""
from .recommendation_compat import analyse


class SimilarPartsRecommender:
    def __init__(self, graph):
        self._graph = graph

    def recommend(self, part_name, top_n=10, scope=None, node_id=None):
        return analyse(self._graph, 'similar', part_name, scope, node_id, top_n)