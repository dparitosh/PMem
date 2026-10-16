"""Package tracked source files, excluding workstation evidence and runtime data."""
import argparse
from pathlib import Path, PurePosixPath
import subprocess
import zipfile

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
