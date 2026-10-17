"""Run the production row builder with dependency-free graph fixtures."""
import ast
from pathlib import Path


def install_projection_fixture(scope):
    from backend.depo_platform.ontology_semantics import kind
    scope['kind'] = kind
    tree = ast.parse(Path('backend/depo_platform/projection_preparation.py').read_text(encoding='utf-8'))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef))
    exec(compile(ast.Module(body=[function], type_ignores=[]), '<projection>', 'exec'), scope)
    graph_factory = scope['prepare_rdf']
    scope['prepare_rdf'] = lambda *args, **kwargs: scope['build_projection'](graph_factory(*args, **kwargs))
