"""Compatibility API for the shared engineering dependency analysis."""
from .recommendation_compat import analyse


class ChangeImpactRecommender:
    def __init__(self, graph):
        self._graph = graph

    def analyse(self, *, change_name='', part_name='', scope=None):
        return analyse(self._graph, 'impact', change_name or part_name, scope)