"""Package tracked source files, excluding workstation evidence and runtime data."""
import argparse
from pathlib import Path, PurePosixPath
import subprocess
import zipfile
import hashlib
import json

EXCLUDED = {'.git', '.codex', 'logs', 'ontology_uploads', 'uploads',
            'node_modules', '__pycache__', '.pytest_cache', '.release-test-tmp',
            '.dt_venv', '.venv', 'venv', '.mypy_cache', '.ruff_cache', 'release-dist',
            '.codex-build', '.codex-pptx-build', '.pptx-review-build'}


def allowed(name):
    path = PurePosixPath(name)
    return (not any(part in EXCLUDED or part.startswith('.dt_venv-') for part in path.parts)
            and path.name not in {'.env', '.env.local', '.env.production', '.env.development', '.env.test'}
            and not path.name.endswith('.local')
            and not (path.name.startswith('.env') and not path.name.endswith(('.example', '.sample')))
            and path.suffix.lower() not in {'.log', '.pyc', '.pyo'})


def package(root, output=None):
    root = Path(root).resolve()
    entries = subprocess.check_output(['git', 'ls-files', '--stage', '-z'], cwd=root).decode('utf-8').split('\0')
    tracked = []
    for entry in entries:
        if not entry:
            continue
        metadata, name = entry.split('\t', 1)
        if metadata.split()[0] == '160000':
            print(f'Excluded Git reference (not packaged source): {name}')
            continue
        if metadata.split()[2] != '0':
            raise ValueError('Resolve Git merge conflicts before packaging')
        tracked.append(name)
    files = [name for name in tracked if name and allowed(name)]
    required = {'INSTALLATION.md', 'install-depo.ps1', 'infra/deployment/services.json',
                'ontology/bill_of_characteristics.ttl', 'ontology/qif_ap242_boc_alignment.ttl'}
    if not required.issubset(files):
        raise ValueError('Tracked release is missing required installation or ontology assets')
    if (root/'backend/ontology_service/owl_dl.py').exists():
        foundation_files = {'backend/ontology_service/owl_dl.py','backend/ontology_service/foundation.py',
            'backend/ontology_service/resources/foundation/manifest.json',
            'backend/ontology_service/resources/foundation/ido-core-4.2.ttl',
            'backend/ontology_service/resources/foundation/depo-business-core.ttl',
            'backend/ontology_service/resources/foundation/NOTICE.md',
            'backend/ontology_service/resources/reasoner/manifest.json',
            'infra/reasoner/THIRD_PARTY.md','infra/reasoner/pom.xml','infra/reasoner/build.ps1',
            'infra/reasoner/src/main/java/org/depo/reasoner/Main.java'}
        if not foundation_files.issubset(files): raise ValueError('Track the complete embedded foundation/reasoner source and notices before packaging')
        foundation_dir = root/'backend/ontology_service/resources/foundation'
        foundation = json.loads((foundation_dir/'manifest.json').read_text())
        for filename, expected in [('ido-core-4.2.ttl',foundation['sha256']),('depo-business-core.ttl',foundation['depo_module_sha256'])]:
            if hashlib.sha256((foundation_dir/filename).read_bytes()).hexdigest() != expected:
                raise ValueError('Embedded foundation checksum mismatch; restore the reviewed resource')
        jar_name = 'backend/ontology_service/resources/reasoner/depo-owl-dl.jar'
        jar = root/jar_name
        reasoner = json.loads((jar.parent/'manifest.json').read_text(encoding='utf-8-sig'))
        if not jar.is_file() or jar.is_symlink() or hashlib.sha256(jar.read_bytes()).hexdigest() != reasoner['sha256']:
            raise ValueError('Build the verified OWL-DL worker before creating a customer release')
        files = sorted(set(files) | {jar_name})
    for name in files:
        path = root / name
        if not path.resolve().is_relative_to(root) or not path.is_file() or path.is_symlink():
            raise ValueError(f'Release source is missing or unsafe: {name}')
    if output:
        output = Path(output).resolve()
        if output.exists():
            raise ValueError('Output already exists; choose a new ZIP filename')
        output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
            for name in files:
                archive.write(root / name, name)
    print(f'PASS: {len(files)} tracked release files; runtime data and development evidence excluded.')
    return files


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', help='New ZIP path; omit to check file selection only')
    args = parser.parse_args()
    package(Path(__file__).resolve().parents[2], args.output)
