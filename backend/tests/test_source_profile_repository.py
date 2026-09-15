from __future__ import annotations

from backend.ingestion_service.profiles import SourceProfileStore
from backend.mesh_store import InMemoryRegistry
import pytest


def test_source_profile_versions_are_control_plane_records(tmp_path, monkeypatch):
    monkeypatch.setenv("DEPO_DATABASE_URL", "postgresql://configured-for-test")
    registry = InMemoryRegistry()
    store = SourceProfileStore(root=tmp_path, registry=registry)

    first = store.save({"profile_id": "parts", "mapping": {"entity": "Part"}})
    second = store.save({"profile_id": "parts", "mapping": {"entity": "Part"}})

    assert first["version"] == 1
    assert second["version"] == 2
    assert store.get("parts")["version"] == 2
    assert registry.get("profile:parts:v1")["version"] == 1
    assert registry.get("profile:parts:current")["version"] == 2


@pytest.mark.parametrize("identifier", ["../outside", "..\\outside", "D:\\outside", "/outside", "CON", "parts:stream"])
def test_profile_paths_reject_unsafe_identifiers(tmp_path, identifier):
    store = SourceProfileStore(root=tmp_path, registry=InMemoryRegistry())
    with pytest.raises(ValueError):
        store.save({"profile_id": identifier})
    with pytest.raises(ValueError):
        store.get(identifier)
