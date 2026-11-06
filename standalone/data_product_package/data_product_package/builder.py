from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable

from .catalog import read_xlsx_catalog
from .models import DataProductSpec


class DataProductBuilder:
    """Build an immutable, checksummed data-product package on the filesystem."""

    def __init__(self, output_dir: str):
        self.output_dir = Path(output_dir).resolve()

    @staticmethod
    def _checksum(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    @staticmethod
    def _safe_name(value: str) -> str:
        return "".join(char if char.isalnum() or char in "-_." else "_" for char in value).strip("._") or "artifact"

    def validate(self, spec: DataProductSpec) -> Dict[str, Any]:
        errors = []
        warnings = []
        if not spec.product_id.strip():
            errors.append("product_id is required")
        if not spec.name.strip():
            errors.append("name is required")
        if not spec.version.strip():
            errors.append("version is required")
        seen = set()
        for artifact in spec.artifacts:
            path = Path(artifact.path).expanduser().resolve()
            if not path.is_file():
                errors.append(f"artifact does not exist: {artifact.path}")
            if str(path) in seen:
                warnings.append(f"duplicate artifact ignored during packaging: {artifact.path}")
            seen.add(str(path))
        if not spec.ontologies:
            warnings.append("no ontology selected; this will be an untyped data product")
        if not spec.sources:
            warnings.append("no source lineage records supplied")
        return {"valid": not errors, "errors": errors, "warnings": warnings}

    def build(self, spec: DataProductSpec, catalog_path: str = "") -> Dict[str, Any]:
        validation = self.validate(spec)
        if not validation["valid"]:
            raise ValueError("Data product validation failed: " + "; ".join(validation["errors"]))

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        product_name = self._safe_name(f"{spec.product_id}-{spec.version}")
        package_dir = self.output_dir / product_name
        zip_path = self.output_dir / f"{product_name}.zip"
        if package_dir.exists() or zip_path.exists():
            raise FileExistsError(f"output already exists for product version: {product_name}")
        package_dir.mkdir(parents=True, exist_ok=False)
        try:
            artifact_records = []
            used_names = set()
            packaged_sources = set()
            for artifact in spec.artifacts:
                source = Path(artifact.path).expanduser().resolve()
                source_key = str(source).casefold()
                if source_key in packaged_sources:
                    continue
                packaged_sources.add(source_key)
                name = self._safe_name(artifact.name or source.name)
                stem, suffix = Path(name).stem, Path(name).suffix
                candidate = name
                index = 2
                while candidate.casefold() in used_names:
                    candidate = f"{stem}-{index}{suffix}"
                    index += 1
                used_names.add(candidate.casefold())
                target = package_dir / "artifacts" / candidate
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                artifact_records.append({
                    **artifact.to_dict(),
                    "name": candidate,
                    "path": f"artifacts/{candidate}",
                    "size": target.stat().st_size,
                    "sha256": self._checksum(target),
                })

            catalog = None
            selected_catalog = catalog_path or spec.catalog_path
            if selected_catalog:
                catalog = read_xlsx_catalog(selected_catalog)
                (package_dir / "catalog.json").write_text(json.dumps(catalog, indent=2), encoding="utf-8")

            manifest = {
            "manifest_version": "1.0",
            "product_id": spec.product_id,
            "name": spec.name,
            "version": spec.version,
            "domain": spec.domain,
            "description": spec.description,
            "owner": spec.owner,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "build_id": timestamp,
            "ontologies": spec.ontologies,
            "sources": [source.to_dict() for source in spec.sources],
            "artifacts": artifact_records,
            "catalog": "catalog.json" if catalog else None,
            "validation": validation,
            }
            (package_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            readme = f"# {spec.name}\n\nVersion: {spec.version}\nProduct ID: {spec.product_id}\n\nThis package was generated by the standalone builder. See `manifest.json` for lineage and checksums.\n"
            (package_dir / "README.md").write_text(readme, encoding="utf-8")

            with zipfile.ZipFile(zip_path, "x", compression=zipfile.ZIP_DEFLATED) as archive:
                for path in package_dir.rglob("*"):
                    if path.is_file():
                        archive.write(path, path.relative_to(self.output_dir).as_posix())
            return {"directory": str(package_dir), "zip": str(zip_path), "manifest": manifest}
        except Exception:
            shutil.rmtree(package_dir, ignore_errors=True)
            zip_path.unlink(missing_ok=True)
            raise
