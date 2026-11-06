"""Preview or remove only reproducible repository caches; never business artifacts."""
import argparse
import json
import os
from pathlib import Path
import shutil

CACHES = {'.pytest_cache', '.mypy_cache', '.ruff_cache', '__pycache__', '.vite', '.vite-temp'}
EXCLUDED = {'.git', 'node_modules', 'data', 'uploads', 'ontology_uploads', 'logs',
            'external', 'outputs', 'deliverables', 'dist', '.venv', 'venv'}


def linked(path):
    return path.is_symlink() or path.is_junction()


def candidates(root):
    root = root.resolve()
    for directory, names, _ in os.walk(root, followlinks=False):
        for name in list(names):
            path = Path(directory) / name
            if name.casefold() in EXCLUDED or name.casefold().startswith('.dt_venv') or linked(path):
                names.remove(name)
            elif name in CACHES:
                names.remove(name)
                # Do not delete a cache containing a junction/symlink: Windows
                # tooling may use those to reference files outside the checkout.
                unsafe = False
                for parent, dirs, files in os.walk(path, followlinks=False):
                    if any(linked(Path(parent) / child) for child in dirs + files):
                        unsafe = True
                        break
                if not unsafe:
                    yield path


def clean(root, apply=False):
    root = root.resolve()
    if not (root / 'infra/deployment/services.json').is_file():
        raise ValueError('Expected a DEPO repository root')
    results = []
    failures = []
    for path in candidates(root):
        resolved = path.resolve()
        if resolved == root or not resolved.is_relative_to(root) or linked(path):
            raise ValueError('Unsafe cache path')
        try:
            count = sum(file.stat().st_size for file in path.rglob('*') if file.is_file())
            if apply:
                shutil.rmtree(path)
        except OSError as exc:
            failures.append({'path': str(path.relative_to(root)), 'error': type(exc).__name__})
            continue
        results.append({'path': str(path.relative_to(root)), 'bytes': count})
    return {'applied': apply, 'bytes': sum(row['bytes'] for row in results),
            'caches': results, 'failures': failures}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Remove listed caches after stopping builds/tests')
    args = parser.parse_args()
    print(json.dumps(clean(Path(__file__).resolve().parents[2], args.apply), indent=2))
