"""Immutable package builder used by the Data Product API."""
from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
import re
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


def build_package(*, output_root: Path, payload: dict, artifacts: list[tuple[dict, Path]]) -> dict:
    digest = publication_digest(payload, artifacts)
    product_id, version = str(payload["product_id"]), str(payload["version"])
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9._-]{0,127}", product_id):
        raise ValueError("product_id must be a safe identifier")
    if not re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?", version):
        raise ValueError("version must use semantic versioning")
    packages_root = (output_root / "packages").resolve()
    package_dir = output_root / "packages" / product_id / version
    if not package_dir.resolve().is_relative_to(packages_root):
        raise ValueError("Product package path is outside product storage")
    zip_path = output_root / "packages" / product_id / f"{version}.zip"
    if package_dir.exists() or zip_path.exists():
        manifest = package_dir / "manifest.json"
        if manifest.is_file() and zip_path.is_file():
            existing = json.loads(manifest.read_text(encoding="utf-8"))
            if existing.get('publication_digest') != digest:
                raise ValueError('Existing product package has different or unverified content; publish a new version')
            try:
                expected = {'manifest.json'}
                with zipfile.ZipFile(zip_path) as archive:
                    if archive.testzip() is not None or json.loads(archive.read('manifest.json')) != existing:
                        raise ValueError('Package archive is corrupt or has a different manifest')
                    for item in existing['artifacts']:
                        name = item['package_path']
                        path = (package_dir / name).resolve()
                        if not path.is_relative_to(package_dir.resolve()) or not path.is_file():
                            raise ValueError('Package artifact is missing or unsafe')
                        if _checksum(path) != item['sha256'] or hashlib.sha256(archive.read(name)).hexdigest() != item['sha256']:
                            raise ValueError('Package artifact checksum does not match')
                        expected.add(name)
                    names = archive.namelist()
                    if len(names) != len(expected) or set(names) != expected:
                        raise ValueError('Package archive contains unexpected or duplicate members')
            except (OSError, zipfile.BadZipFile, KeyError, TypeError, ValueError) as exc:
                raise ValueError('Existing product package failed integrity verification; restore it before retrying') from exc
            return {"manifest": existing, "package_dir": package_dir, "zip_path": zip_path}
        raise ValueError("product version package already exists but is incomplete")
    package_dir.mkdir(parents=True, exist_ok=False)
    try:
        records = []
        for metadata, source in artifacts:
            target = package_dir / "artifacts" / metadata["artifact_id"].split(":", 1)[1]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            records.append({**metadata, "package_path": target.relative_to(package_dir).as_posix(), "sha256": _checksum(target)})
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
        (package_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        with zipfile.ZipFile(zip_path, "x", compression=zipfile.ZIP_DEFLATED) as archive:
            for item in package_dir.rglob("*"):
                if item.is_file(): archive.write(item, item.relative_to(package_dir).as_posix())
        return {"manifest": manifest, "package_dir": package_dir, "zip_path": zip_path}
    except Exception:
        shutil.rmtree(package_dir, ignore_errors=True)
        zip_path.unlink(missing_ok=True)
        raise
