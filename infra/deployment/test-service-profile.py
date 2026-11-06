"""Smoke-check a service while blocking distributions outside its reviewed lock.

Run in a release test environment containing the union of service dependencies.
Each invocation is a new process: optional fallback imports are allowed to fail,
but required imports must succeed without borrowing another service's packages.
This checks imports/OpenAPI generation, not live integrations or every handler.
"""
import argparse
import builtins
from importlib.abc import MetaPathFinder
from importlib import metadata
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def canonical(value):
    return re.sub(r'[-_.]+', '-', value).lower()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--service', required=True)
    args = parser.parse_args()
    manifest = json.loads((ROOT / 'infra/deployment/services.json').read_text())
    if args.service not in {entry['id'] for entry in manifest['services'] + manifest['workers']}:
        raise ValueError('Unknown deployment service')
    lock = ROOT / 'backend/dependency-profiles' / (args.service + '.txt')
    allowed = {line.split('==')[0] for line in lock.read_text().splitlines() if '==' in line}
    mapping = metadata.packages_distributions()
    original_import = builtins.__import__

    class ProfileFinder(MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            top = fullname.split('.')[0]
            owners = mapping.get(top, [])
            if owners and top not in sys.stdlib_module_names and not any(canonical(owner) in allowed for owner in owners):
                raise ModuleNotFoundError(f'Distribution is outside service profile: {top}', name=top)
            return None

    def guarded_import(name, *positional, **keyword):
        level = keyword.get('level', positional[3] if len(positional) > 3 else 0)
        if level:
            return original_import(name, *positional, **keyword)
        top = name.split('.')[0]
        owners = mapping.get(top, [])
        if owners and top not in sys.stdlib_module_names and not any(canonical(owner) in allowed for owner in owners):
            raise ModuleNotFoundError(f'Distribution is outside service profile: {top}', name=top)
        return original_import(name, *positional, **keyword)

    builtins.__import__ = guarded_import
    finder = ProfileFinder()
    sys.meta_path.insert(0, finder)
    try:
        from backend.depo_platform.service_smoke import check
        print(json.dumps({**check(args.service), 'profile_guard': 'enabled'}))
    finally:
        builtins.__import__ = original_import
        sys.meta_path.remove(finder)
