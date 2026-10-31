"""Read-only dependency footprint. Never infer uninstall safety from imports alone."""
import argparse
import importlib.metadata as metadata
import json
from pathlib import Path
import re


def canonical(name):
    return re.sub(r'[-_.]+', '-', name).lower()


def lock_names(path):
    return {canonical(line.split('==')[0]) for line in path.read_text().splitlines()
            if line and not line.startswith('#') and '==' in line}


def inventory(root):
    base = lock_names(root / 'backend/requirements-lock.txt')
    optional = lock_names(root / 'backend/requirements-ocr-lock.txt') - base
    rows = []
    for distribution in metadata.distributions():
        name = canonical(distribution.metadata['Name'])
        # RECORD sizes avoid walking model directories or following links.
        size = sum(file.size or 0 for file in distribution.files or [])
        rows.append({'name': name, 'version': distribution.version, 'record_bytes': size,
                     'profile': 'runtime' if name in base else 'optional-ocr' if name in optional else 'outside-release-lock'})
    return {'measurement': 'Distribution RECORD bytes; shared files can be counted twice. Not physical disk usage.',
            'uninstall_safe': False, 'runtime_lock_packages': len(base),
            'optional_ocr_lock_packages': len(optional),
            'distributions': sorted(rows, key=lambda row: (-row['record_bytes'], row['name']))}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    report = json.dumps(inventory(Path(__file__).resolve().parents[2]), indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report + '\n', encoding='utf-8')
    else:
        print(report)
