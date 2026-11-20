"""Build the independent Engineering ODS toolkit without customer runtime state."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

FILES = (
    'nexus_ods.py', 'README.md', 'requirements.txt', 'config.example.json',
    'scenario.json', 'test_toolkit.py', 'acceptance-questions.txt',
    'assets/schema.ttl', 'assets/shapes.ttl',
    'sample-output/engineering-ods.ttl', 'sample-output/manifest.json',
    'sample-output/identities.json', 'sample-output/relationships.json',
)


def package(root, output):
    root, output = Path(root).resolve(), Path(output).resolve()
    source = root / 'standalone/engineering_ods'
    selected = []
    for name in FILES:
        path = source / name
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(source):
            raise ValueError('Incomplete standalone toolkit source: ' + name)
        selected.append((name, path.read_bytes()))
    config = json.loads((source / 'config.example.json').read_text(encoding='utf-8-sig'))
    if set(config) - {'name', 'prefix', 'namespace', 'case_key', 'family_id', 'version', 'scenario', 'output',
                      'ontology_api', 'oslc_api', 'read_token_env', 'write_token_env'}:
        raise ValueError('Example config contains unexpected settings; review for customer secrets')
    if output.exists():
        raise ValueError('Output already exists; choose a new archive filename')
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in selected:
            info = zipfile.ZipInfo('NEXUS-Engineering-ODS-Toolkit/' + name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, content)
    return {'archive': str(output), 'files': len(selected), 'sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
            'customer_credentials_included': False, 'customer_registration_state_included': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(package(Path(__file__).resolve().parents[1], args.output), indent=2))
    except (OSError, ValueError) as exc:
        parser.exit(1, str(exc) + '\n')
