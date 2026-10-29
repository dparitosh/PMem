"""Run the production row builder with dependency-free graph fixtures."""
import ast
from pathlib import Path


def install_projection_fixture(scope):
    from backend.depo_platform.projection_preparation import build_projection
    scope['build_projection'] = build_projection
    graph_factory = scope['prepare_rdf']
    scope['prepare_rdf'] = lambda *args, **kwargs: scope['build_projection'](graph_factory(*args, **kwargs))
