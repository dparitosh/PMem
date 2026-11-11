"""Compatibility entry point for the canonical customer source packager."""
import argparse
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location('depo_release_package', ROOT / 'infra/deployment/build-release-package.py')
_release = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_release)

def permitted(relative):
    return _release.allowed(Path(relative).as_posix())

def build(output):
    return _release.package(ROOT, output)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default=str(ROOT / 'release-dist/DEPO-customer-source.zip'))
    build(parser.parse_args().output)
