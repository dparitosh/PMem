"""Immutable package builder used by the Data Product API."""
from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
import re
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path


def _checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def publication_digest(payload: dict, artifacts: list[tuple[dict, Path]]) -> str:
    ignored = {'approval_token', 'authorization', 'api_key', 'approved_by', 'idempotency_key'}
    content = {key: value for key, value in payload.items() if key not in ignored and key != 'artifacts'}
    content['artifacts'] = sorted(({'artifact_id': m['artifact_id'], 'sha256': _checksum(path)} for m, path in artifacts), key=lambda item: item['artifact_id'])
    return hashlib.sha256(json.dumps(content, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def verify_package(package_dir: Path, zip_path: Path, expected_manifest=None) -> dict:
    """Verify retained content and ZIP members using bounded streaming reads."""
    try:
        manifest_path = package_dir / 'manifest.json'
        if manifest_path.stat().st_size > 8 * 1024 * 1024:
            raise ValueError('Retained manifest exceeds the size limit')
        existing = json.loads(manifest_path.read_text(encoding='utf-8'))
        if expected_manifest is not None and existing != expected_manifest:
            raise ValueError('Retained manifest differs from the registered manifest')
        expected = {'manifest.json'}
        with zipfile.ZipFile(zip_path) as archive:
            with archive.open('manifest.json') as stream:
                content = stream.read(8 * 1024 * 1024 + 1)
            if len(content) > 8 * 1024 * 1024 or json.loads(content) != existing:
                raise ValueError('Archive manifest mismatch')
            for item in existing['artifacts']:
                name = item['package_path']
                path = (package_dir / name).resolve()
                if not path.is_relative_to(package_dir.resolve()) or not path.is_file():
                    raise ValueError('Package artifact is missing or unsafe')
                checksum = hashlib.sha256()
                with archive.open(name) as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b''):
                        checksum.update(block)
                if _checksum(path) != item['sha256'] or checksum.hexdigest() != item['sha256']:
                    raise ValueError('Package artifact checksum mismatch')
                expected.add(name)
            names = archive.namelist()
            if len(names) != len(expected) or set(names) != expected:
                raise ValueError('Unexpected or duplicate archive members')
        return existing
    except (OSError, zipfile.BadZipFile, KeyError, TypeError, ValueError, RuntimeError) as exc:
        raise ValueError('Retained product package failed integrity verification') from exc


def build_package(*, output_root: Path, payload: dict, artifacts: list[tuple[dict, Path]]) -> dict:
    digest = publication_digest(payload, artifacts)
    product_id, version = str(payload["product_id"]), str(payload["version"])
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9._-]{0,127}", product_id):
        raise ValueError("product_id must be a safe identifier")
    if product_id.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1,10)), *(f'LPT{i}' for i in range(1,10))} or product_id.endswith('.'):
        raise ValueError('product_id is not a portable filesystem identifier')
    if not re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?", version):
        raise ValueError("version must use semantic versioning")
    packages_root = (output_root / "packages").resolve()
    package_dir = output_root / "packages" / product_id / version
    if not package_dir.resolve().is_relative_to(packages_root):
        raise ValueError("Product package path is outside product storage")
    zip_path = package_dir / 'package.zip'
    legacy_zip = output_root / "packages" / product_id / f"{version}.zip"
    if legacy_zip.exists(): zip_path = legacy_zip
    if package_dir.exists() or zip_path.exists():
        manifest = package_dir / "manifest.json"
        if manifest.is_file() and zip_path.is_file():
            existing = json.loads(manifest.read_text(encoding="utf-8"))
            if existing.get('publication_digest') != digest:
                raise ValueError('Existing product package has different or unverified content; publish a new version')
            verify_package(package_dir, zip_path, existing)
            return {"manifest": existing, "package_dir": package_dir, "zip_path": zip_path}
        raise ValueError("product version package already exists but is incomplete")
    final_dir = package_dir
    package_dir = final_dir.parent / ('.staging-' + uuid.uuid4().hex)
    zip_path = package_dir / 'package.zip'
    package_dir.mkdir(parents=True, exist_ok=False)
    try:
        records = []
        for metadata, source in artifacts:
            target = package_dir / "artifacts" / metadata["artifact_id"].split(":", 1)[1]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            checksum = _checksum(target)
            if metadata.get('sha256') and checksum != metadata['sha256']:
                raise ValueError('Artifact source changed from its retained content address')
            records.append({**metadata, "package_path": target.relative_to(package_dir).as_posix(), "sha256": checksum})
        if publication_digest(payload, [(metadata, package_dir / record['package_path']) for (metadata, _), record in zip(artifacts, records)]) != digest:
            raise ValueError('Artifact source changed during packaging; retry with immutable content')
        manifest = {
            "publication_digest": digest,
            "manifest_version": "1.0", "product_id": product_id, "name": payload["name"], "version": version,
            "domain": payload["domain"], "owner": payload["owner"], "description": payload.get("description", ""),
            "classification": payload.get("classification", "internal"), "steward": payload.get("steward", payload["owner"]),
            "sla": payload.get("sla", {}), "quality_status": payload.get("quality_status", "not_assessed"),
            "product_kind": payload.get("product_kind"), "analytics_readiness": payload.get("analytics_readiness"),
            "sources": payload.get("sources", []), "ontologies": payload.get("ontologies", []),
            "semantic_releases": payload.get("semantic_releases", []), "artifacts": records,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        manifest_text = json.dumps(manifest, indent=2)
        if len(manifest_text.encode('utf-8')) > 8 * 1024 * 1024:
            raise ValueError('Product manifest exceeds the 8 MiB retention limit')
        (package_dir / "manifest.json").write_text(manifest_text, encoding="utf-8")
        with zipfile.ZipFile(zip_path, "x", compression=zipfile.ZIP_DEFLATED) as archive:
            for item in package_dir.rglob("*"):
                if item.is_file() and item != zip_path: archive.write(item, item.relative_to(package_dir).as_posix())
        verify_package(package_dir, zip_path, manifest)
        os.rename(package_dir, final_dir)
        return {"manifest": manifest, "package_dir": final_dir, "zip_path": final_dir / 'package.zip'}
    except Exception:
        shutil.rmtree(package_dir, ignore_errors=True)
        zip_path.unlink(missing_ok=True)
        raise
