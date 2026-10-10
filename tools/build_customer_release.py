"""Build a source installation ZIP without developer state or customer secrets."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DIRECTORIES = {"backend", "frontend", "config", "infra", "scripts", "tools",
               "docs", "data", "ontology", "mapping", "parsers", "plugins", "standalone", "deliverables"}
ROOT_FILES = {"INSTALLATION.md", "README.md", "main.py", "install-depo.ps1",
              "configure-depo.ps1", "diagnose-depo.ps1", "manage-depo.ps1", "certify-depo-release.ps1"}
EXCLUDED_NAMES = {"node_modules", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
                  ".venv", "venv", ".dt_venv", "dist", "build", "test-results", "playwright-report",
                  "tests", "test_data", "ttl_cache", ".env-reference-review", ".git", ".codex"}
EXCLUDED_PREFIXES = ("data/products/", "data/parser_outputs/", "data/artifacts/", "data/code_audit/", "data/ontology_service/",
                     "data/source_profiles/", "docs/audits/", "backend/STP/", "backend/Data/")


def permitted(relative):
    path = Path(relative)
    parts = path.parts
    normalized = path.as_posix()
    if any(part in EXCLUDED_NAMES for part in parts):
        return False
    if normalized.startswith(EXCLUDED_PREFIXES):
        return False
    if any(part.startswith(".env") and not part.endswith(".example") for part in parts):
        return False
    if path.suffix.lower() in {".log", ".pyc", ".pyo", ".tmp", ".bak"}:
        return False
    if path.name.startswith(("test_", "test-")) and path.suffix == ".py":
        return False
    if path.name.endswith((".test.js", ".test.jsx", ".test.ts", ".test.tsx", ".spec.js", ".spec.ts")):
        return False
    if path.name.startswith(("repository-cleanup", "customer-release-cleanup", "rpa-cleanup")):
        return False
    return parts[0] in DIRECTORIES if len(parts) > 1 else normalized in ROOT_FILES


def build(output):
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("Output already exists; select a new release filename")
    files = []
    for directory in sorted(DIRECTORIES):
        start = ROOT / directory
        if not start.exists():
            continue
        for current, folders, names in os.walk(start, followlinks=False):
            folders[:] = sorted(folder for folder in folders
                                 if folder not in EXCLUDED_NAMES and not (Path(current) / folder).is_symlink())
            for name in sorted(names):
                file = Path(current) / name
                if file.is_symlink():
                    raise ValueError(f"Release input cannot be a symlink: {file.relative_to(ROOT)}")
                if permitted(file.relative_to(ROOT)):
                    files.append(file)
    files.extend(ROOT / name for name in sorted(ROOT_FILES) if (ROOT / name).is_file())
    required = {"INSTALLATION.md", "backend/requirements-lock.txt", "frontend/package-lock.json",
                "infra/deployment/services.json", "infra/windows/apply-depo-service-credentials.ps1"}
    included = {file.relative_to(ROOT).as_posix() for file in files}
    if required - included:
        raise ValueError(f"Missing release inputs: {sorted(required - included)}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    if temporary.exists():
        raise ValueError("Temporary output already exists")
    records = []
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for file in sorted(files):
                if file.resolve() in {output, temporary}:
                    raise ValueError("Output overlaps release inputs")
                relative = file.relative_to(ROOT).as_posix()
                content = file.read_bytes()
                archive.writestr(relative, content)
                records.append({"path": relative, "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()})
            archive.writestr("release-file-manifest.json", json.dumps({"files": records}, indent=2))
        with zipfile.ZipFile(temporary) as archive:
            if archive.testzip() is not None:
                raise ValueError("ZIP integrity check failed")
        temporary.rename(output)
    finally:
        temporary.unlink(missing_ok=True)
    print(json.dumps({"status": "ok", "files": len(records), "output": str(output), "bytes": output.stat().st_size}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(ROOT / "release-dist" / "DEPO-customer-source.zip"))
    build(parser.parse_args().output)
