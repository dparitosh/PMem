"""Build/check Windows service locks from reviewed metadata and release pins.

Build tool only: requires packaging. Never contacts a package index or changes
the production dependency versions. Refresh metadata and full lock together in
the release-build environment before upgrading third-party packages.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
from packaging.markers import default_environment
from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[2]
PROFILES = ROOT / 'backend/dependency-profiles'


def canonical(name):
    return re.sub(r'[-_.]+', '-', name).lower()


def resolve(roots, metadata):
    environment = {**default_environment(), 'python_version': '3.12',
                   'python_full_version': '3.12.14', 'sys_platform': 'win32',
                   'platform_system': 'Windows', 'platform_machine': 'AMD64', 'os_name': 'nt',
                   'implementation_name': 'cpython', 'platform_python_implementation': 'CPython'}
    pending, seen = list(roots), set()
    while pending:
        request = Requirement(pending.pop())
        name = canonical(request.name)
        if name not in metadata:
            raise ValueError(f'Unpinned dependency: {name}')
        record = metadata[name]
        if not request.specifier.contains(record['version'], prereleases=True):
            raise ValueError(f'Incompatible dependency pin: {request}')
        for extra in request.extras or {''}:
            if (name, extra) in seen:
                continue
            seen.add((name, extra))
            for raw in record['requires_dist']:
                dependency = Requirement(raw)
                if not dependency.marker or dependency.marker.evaluate({**environment, 'extra': extra}):
                    pending.append(str(dependency))
    return sorted({name for name, _extra in seen})


def generate(check=False):
    metadata = json.loads((PROFILES / 'windows-metadata.json').read_text())
    pins = {}
    for path in [ROOT / 'backend/requirements-lock.txt', ROOT / 'backend/requirements-ocr-lock.txt']:
        for line in path.read_text().splitlines():
            if not line or line.startswith('#'):
                continue
            requirement = Requirement(line.split(' --hash=')[0])
            name = canonical(requirement.name)
            record = metadata.get(name)
            if not record or str(requirement.specifier) != '==' + record['version']:
                raise ValueError(f'Metadata does not match release pin: {name}')
            if record['artifact_sha256'] not in line:
                raise ValueError(f'Metadata artifact hash does not match release pin: {name}')
            pins[name] = line
    summary = {}
    for source in sorted(PROFILES.glob('*.in')):
        roots = [line.strip() for line in source.read_text().splitlines() if line.strip() and not line.startswith('#')]
        selected = resolve(roots, metadata)
        output = '# Generated for CPython 3.12 Windows x64; keep aligned with the release lock.\n'
        output += '# Source: ' + source.name + '; regenerate with infra/deployment/build-service-locks.py\n'
        output += '\n'.join(pins[name] for name in selected) + '\n'
        target = source.with_suffix('.txt')
        if check:
            if not target.is_file() or target.read_text() != output:
                raise ValueError(f'Service lock requires regeneration: {target.name}')
        else:
            target.write_text(output, encoding='utf-8')
        summary[source.stem] = {'packages': len(selected), 'roots': roots}
    report = json.dumps(summary, indent=2) + '\n'
    report_path = PROFILES / 'package-counts.json'
    if check:
        if report_path.read_text() != report:
            raise ValueError('Service package-count report requires regeneration')
    else:
        report_path.write_text(report, encoding='utf-8')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    print(json.dumps({name: row['packages'] for name, row in generate(args.check).items()}))
