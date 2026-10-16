"""Detect mixed XSD converter releases without importing optional runtimes."""
import ast
import argparse
import hashlib
import json
import os
from pathlib import Path


def check(root):
    root = Path(root)
    semantics = root/'backend/Services/xsd_semantics.py'
    engine = root/'backend/Services/owl_xsd_engine.py'
    tree = ast.parse(semantics.read_text(encoding='utf-8'))
    functions = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
    if not {'qualify_schema_types', 'validate_xsd_schema_set'}.issubset(functions):
        raise ValueError('Outdated xsd_semantics.py. Deploy the complete current backend release before starting services.')
    if 'conversion requires namespace-qualified type identities' in semantics.read_text(encoding='utf-8'):
        raise ValueError('Legacy namespace rejection remains in xsd_semantics.py; deploy the current release.')
    engine_tree = ast.parse(engine.read_text(encoding='utf-8'))
    collector = next(node for node in engine_tree.body if isinstance(node, ast.FunctionDef) and node.name == '_collect_simple_types')
    if 'schema_roots' not in {arg.arg for arg in collector.args.args}:
        raise ValueError('Mixed converter release: owl_xsd_engine.py lacks namespace-aware datatype collection.')
    digest = hashlib.sha256()
    for directory, folders, filenames in os.walk(root/'backend'):
        folders[:] = sorted(folder for folder in folders
                            if folder not in {'tests', '__pycache__', '.dt_venv', '.venv', 'venv', 'node_modules'}
                            and not folder.startswith('.dt_venv-'))
        for filename in sorted(filenames):
            if filename.endswith('.py'):
                path = Path(directory)/filename
                digest.update(path.relative_to(root).as_posix().encode()+b'\0'+path.read_bytes()+b'\0')
    return {'status': 'ok', 'backend_fingerprint': digest.hexdigest()}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default=str(Path(__file__).resolve().parents[2]))
    args = parser.parse_args()
    try:
        print(json.dumps(check(args.root)))
    except (OSError, ValueError, SyntaxError, StopIteration) as exc:
        print(json.dumps({'status': 'failed', 'action': str(exc)}))
        raise SystemExit(1)
