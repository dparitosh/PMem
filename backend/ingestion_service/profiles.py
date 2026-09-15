"""Declarative source profiles for user-configured semantic ingestion."""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from defusedxml import ElementTree as ET

from backend.mesh_store import PostgresRegistry


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SourceProfileStore:
    """Versioned profile control-plane repository.

    PostgreSQL is the source of truth when configured. The JSON files are an
    artifact/recovery mirror and allow an explicitly unconfigured local demo.
    """

    def __init__(self, root: Path | None = None, registry: Any | None = None) -> None:
        self.root = root or Path(os.getenv("SOURCE_PROFILE_STORAGE") or Path(__file__).resolve().parents[2] / "data" / "source_profiles")
        self.root.mkdir(parents=True, exist_ok=True)
        self.registry = registry or PostgresRegistry("ingestion_source_profiles")

    @property
    def _postgres_enabled(self) -> bool:
        return bool(os.getenv("DEPO_DATABASE_URL") or os.getenv("DATABASE_URL"))

    @staticmethod
    def _validate_id(profile_id: str) -> str:
        if not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_-]{0,127}", profile_id):
            raise ValueError("profile_id must start with a letter and contain only letters, digits, underscores or hyphens")
        if profile_id.upper() in {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1, 10)], *[f"LPT{i}" for i in range(1, 10)]}:
            raise ValueError("profile_id is a reserved filename")
        return profile_id

    @staticmethod
    def _version_key(profile_id: str, version: int) -> str:
        return f"profile:{profile_id}:v{version}"

    @staticmethod
    def _current_key(profile_id: str) -> str:
        return f"profile:{profile_id}:current"

    def _save(self, profile: dict[str, Any]) -> dict[str, Any]:
        self._validate_id(str(profile["profile_id"]))
        if self._postgres_enabled:
            self.registry.put_many({
                self._version_key(profile["profile_id"], int(profile["version"])): profile,
                self._current_key(profile["profile_id"]): profile,
            })
        (self.root / f"{profile['profile_id']}.json").write_text(json.dumps(profile, indent=2), encoding="utf-8")
        return profile

    def inspect(self, *, filename: str, content: bytes) -> dict[str, Any]:
        suffix = Path(filename).suffix.lower()
        fingerprint = hashlib.sha256(content).hexdigest()
        if suffix == ".xsd":
            root = ET.fromstring(content)
            xs = "{http://www.w3.org/2001/XMLSchema}"
            return {"format": "xsd", "fingerprint": fingerprint, "namespace": root.get("targetNamespace", ""),
                    "entities": [node.get("name") for node in root.findall(f"{xs}complexType") if node.get("name")],
                    "elements": [node.get("name") for node in root.findall(f"{xs}element") if node.get("name")]}
        if suffix in {".json", ".jsonld", ".json-ld"}:
            payload = json.loads(content.decode("utf-8"))
            sample = payload[0] if isinstance(payload, list) and payload else payload
            return {"format": "jsonld" if isinstance(sample, dict) and "@context" in sample else "json", "fingerprint": fingerprint,
                    "namespace": sample.get("@context", "") if isinstance(sample, dict) else "",
                    "fields": sorted(sample.keys()) if isinstance(sample, dict) else []}
        root = ET.fromstring(content)
        return {"format": "xml", "fingerprint": fingerprint, "root": root.tag,
                "attributes": sorted(root.attrib), "children": sorted({child.tag for child in root})}

    def save(self, profile: dict[str, Any]) -> dict[str, Any]:
        profile_id = str(profile.get("profile_id") or profile.get("name", "")).strip().replace(" ", "-").lower()
        if not profile_id:
            raise ValueError("profile_id or name is required")
        self._validate_id(profile_id)
        if self._postgres_enabled:
            with self.registry.advisory_lock(f"version:{profile_id}") as acquired:
                if not acquired:
                    raise ValueError("Source profile is being updated; retry the request")
                return self._save_next_version(profile, profile_id)
        return self._save_next_version(profile, profile_id)

    def _save_next_version(self, profile: dict[str, Any], profile_id: str) -> dict[str, Any]:
        current = self.get(profile_id, required=False)
        current_version = int((current or {}).get("version", 0))
        requested_version = int(profile.get("version", 0))
        profile = {
            **profile,
            "profile_id": profile_id,
            "version": max(current_version + 1, requested_version or 1),
            "updated_at": _now(),
        }
        return self._save(profile)

    def get(self, profile_id: str, *, required: bool = True) -> dict[str, Any] | None:
        self._validate_id(profile_id)
        if self._postgres_enabled:
            profile = self.registry.get(self._current_key(profile_id))
            if profile is not None:
                return profile
        path = self.root / f"{profile_id}.json"
        if path.exists():
            profile = json.loads(path.read_text(encoding="utf-8"))
            if self._postgres_enabled:
                self._save(profile)
            return profile
        if required:
            raise KeyError("Source profile not found")
        return None

    def list(self) -> list[dict[str, Any]]:
        entries = []
        if self._postgres_enabled:
            entries = [
                value for key, value in self.registry.all().items()
                if key.startswith("profile:") and key.endswith(":current") and isinstance(value, dict)
            ]
        known = {str(item.get("profile_id") or "") for item in entries}
        for path in self.root.glob("*.json"):
            profile = json.loads(path.read_text(encoding="utf-8"))
            if str(profile.get("profile_id") or "") not in known:
                if self._postgres_enabled:
                    self._save(profile)
                entries.append(profile)
        return sorted(entries, key=lambda item: str(item.get("profile_id") or ""))

    def normalize(self, *, profile: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
        mapping = profile.get("mapping", {})
        entity_type = mapping.get("entity") or profile.get("name") or "Entity"
        properties = {
            target: value for source, target in mapping.get("properties", {}).items()
            if (value := self._value_at(record, source)) is not None
        }
        identifier = self._value_at(record, mapping.get("identifier", "id")) or record.get("id") or hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()[:16]
        return {"entities": [{"id": str(identifier), "type": entity_type, **properties}], "relationships": [],
                "provenance": {"profile_id": profile["profile_id"], "profile_version": profile["version"]}}

    @staticmethod
    def _value_at(record: dict[str, Any], path: str) -> Any:
        """Read a simple dotted source path without allowing code expressions."""
        value: Any = record
        for part in str(path or "").replace("/", ".").split("."):
            if not part:
                continue
            if not isinstance(value, dict):
                return None
            value = value.get(part)
        return value

    @staticmethod
    def _local_name(tag: str) -> str:
        return str(tag).rsplit("}", 1)[-1]

    def _xml_record(self, element: Any) -> dict[str, Any]:
        record: dict[str, Any] = {self._local_name(key): value for key, value in element.attrib.items()}
        for child in element:
            key = self._local_name(child.tag)
            value = (child.text or "").strip()
            if len(child):
                value = self._xml_record(child)
            if key in record:
                record[key] = record[key] + [value] if isinstance(record[key], list) else [record[key], value]
            else:
                record[key] = value
        return record

    def extract_records(self, *, profile: dict[str, Any], filename: str, content: bytes) -> list[dict[str, Any]]:
        """Convert an uploaded JSON, JSON-LD or XML batch into safe record dictionaries."""
        suffix = Path(filename).suffix.lower()
        mapping = profile.get("mapping", {})
        record_path = str(mapping.get("records_path") or profile.get("records_path") or "").strip()
        if suffix in {".json", ".jsonld", ".json-ld"}:
            payload: Any = json.loads(content.decode("utf-8"))
            if record_path:
                payload = self._value_at(payload, record_path) if isinstance(payload, dict) else None
            if isinstance(payload, list):
                return [item for item in payload if isinstance(item, dict)]
            return [payload] if isinstance(payload, dict) else []

        root = ET.fromstring(content)
        if record_path:
            selected: Iterable[Any] = root.findall(record_path)
        elif len(root):
            selected = list(root)
        else:
            selected = [root]
        return [self._xml_record(element) for element in selected]

    def normalize_batch(self, *, profile: dict[str, Any], filename: str, content: bytes) -> dict[str, Any]:
        records = self.extract_records(profile=profile, filename=filename, content=content)
        entities: list[dict[str, Any]] = []
        relationships: list[dict[str, Any]] = []
        for record in records:
            normalized = self.normalize(profile=profile, record=record)
            entities.extend(normalized["entities"])
            relationships.extend(normalized["relationships"])
        return {
            "entities": entities,
            "relationships": relationships,
            "records_processed": len(records),
            "provenance": {"profile_id": profile["profile_id"], "profile_version": profile["version"], "source_filename": filename},
        }


profiles = SourceProfileStore()
