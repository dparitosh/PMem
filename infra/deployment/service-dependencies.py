"""Conservative per-service Python import inventory (includes lazy imports).

This inventories repository imports, not runtime execution. Dynamic plugin paths
and optional external runtimes must additionally pass the service smoke checks.
"""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import sys
from functools import lru_cache

ROOT = Path(__file__).resolve().parents[2]
IMPORT_DISTRIBUTIONS = {
    'PIL': 'pillow', 'yaml': 'pyyaml', 'dotenv': 'python-dotenv',
    'docx': 'python-docx', 'pptx': 'python-pptx', 'fitz': 'pymupdf',
    'cv2': 'opencv-python', 'sklearn': 'scikit-learn',
    'sentence_transformers': 'sentence-transformers', 'graphql': 'graphql-core',
    'langchain_core': 'langchain-core', 'langchain_neo4j': 'langchain-neo4j',
    'langchain_ollama': 'langchain-ollama', 'langchain_openai': 'langchain-openai',
    'multipart': 'python-multipart',
}


@lru_cache(maxsize=None)
def module_path(module):
    path = ROOT.joinpath(*module.split('.'))
    if path.with_suffix('.py').is_file():
        return path.with_suffix('.py')
    if (path / '__init__.py').is_file():
        return path / '__init__.py'
    return None


def inventory(entry):
    pending, seen, external = [entry.split(':')[0]], set(), set()
    while pending:
        module = pending.pop()
        path = module_path(module)
        if module in seen or not path:
            continue
        seen.add(module)
        package = module if path.name == '__init__.py' else module.rpartition('.')[0]
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))):
            targets = []
            if isinstance(node, ast.Import):
                targets = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ''
                if node.level:
                    parts = package.split('.')
                    base = '.'.join(parts[:len(parts) - node.level + 1] + ([base] if base else []))
                targets = [base] + [base + '.' + alias.name for alias in node.names]
            elif isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                if (isinstance(node.func, ast.Attribute) and node.func.attr == 'import_module') or (isinstance(node.func, ast.Name) and node.func.id == '__import__'):
                    targets = [node.args[0].value]
            for target in targets:
                if module_path(target):
                    pending.append(target)
                elif target and not target.startswith('backend.'):
                    top = target.split('.')[0]
                    if top not in sys.stdlib_module_names and top != '__future__':
                        external.add(top)
    return {'entrypoint': entry, 'repository_modules': sorted(seen),
            'external_imports': sorted(external),
            'distribution_candidates': sorted({IMPORT_DISTRIBUTIONS.get(top, top.replace('_', '-')) for top in external})}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    manifest = json.loads((ROOT / 'infra/deployment/services.json').read_text())
    result = {item['id']: inventory(item['module']) for item in manifest['services'] + manifest['workers']}
    payload = json.dumps(result, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + '\n', encoding='utf-8')
    else:
        print(payload)


if __name__ == '__main__':
    main()
