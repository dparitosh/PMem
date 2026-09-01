"""Declarative source profiles for user-configured semantic ingestion."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from defusedxml import ElementTree as ET


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SourceProfileStore:
    def __init__(self) -> None:
        self.root = Path(__file__).resolve().parents[2] / "data" / "source_profiles"
        self.root.mkdir(parents=True, exist_ok=True)

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
            return {"format": "jsonld" if "@context" in sample else "json", "fingerprint": fingerprint,
                    "namespace": sample.get("@context", "") if isinstance(sample, dict) else "",
                    "fields": sorted(sample.keys()) if isinstance(sample, dict) else []}
        root = ET.fromstring(content)
        return {"format": "xml", "fingerprint": fingerprint, "root": root.tag,
                "attributes": sorted(root.attrib), "children": sorted({child.tag for child in root})}

    def save(self, profile: dict[str, Any]) -> dict[str, Any]:
        profile_id = str(profile.get("profile_id") or profile.get("name", "")).strip().replace(" ", "-").lower()
        if not profile_id:
            raise ValueError("profile_id or name is required")
        profile = {**profile, "profile_id": profile_id, "version": int(profile.get("version", 1)), "updated_at": _now()}
        (self.root / f"{profile_id}.json").write_text(json.dumps(profile, indent=2), encoding="utf-8")
        return profile

    def get(self, profile_id: str) -> dict[str, Any]:
        path = self.root / f"{profile_id}.json"
        if not path.exists(): raise KeyError("Source profile not found")
        return json.loads(path.read_text(encoding="utf-8"))

    def list(self) -> list[dict[str, Any]]:
        return [json.loads(path.read_text(encoding="utf-8")) for path in self.root.glob("*.json")]

    def normalize(self, *, profile: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
        mapping = profile.get("mapping", {})
        entity_type = mapping.get("entity") or profile.get("name") or "Entity"
        properties = {target: record.get(source) for source, target in mapping.get("properties", {}).items() if source in record}
        identifier = record.get(mapping.get("identifier", "id")) or record.get("id") or hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()[:16]
        return {"entities": [{"id": str(identifier), "type": entity_type, **properties}], "relationships": [],
                "provenance": {"profile_id": profile["profile_id"], "profile_version": profile["version"]}}


profiles = SourceProfileStore()
