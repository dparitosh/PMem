"""Immutable package builder used by the Data Product API."""
from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path


def _checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_package(*, output_root: Path, payload: dict, artifacts: list[tuple[dict, Path]]) -> dict:
    product_id, version = str(payload["product_id"]), str(payload["version"])
    package_dir = output_root / "packages" / product_id / version
    zip_path = output_root / "packages" / product_id / f"{version}.zip"
    if package_dir.exists() or zip_path.exists():
        manifest = package_dir / "manifest.json"
        if manifest.is_file() and zip_path.is_file():
            return {"manifest": json.loads(manifest.read_text(encoding="utf-8")), "package_dir": package_dir, "zip_path": zip_path}
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
            "manifest_version": "1.0", "product_id": product_id, "name": payload["name"], "version": version,
            "domain": payload["domain"], "owner": payload["owner"], "description": payload.get("description", ""),
            "classification": payload.get("classification", "internal"), "steward": payload.get("steward", payload["owner"]),
            "sla": payload.get("sla", {}), "quality_status": payload.get("quality_status", "not_assessed"),
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
