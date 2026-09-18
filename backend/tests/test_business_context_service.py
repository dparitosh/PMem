from pathlib import Path

from backend.ontology_service.business_context import BusinessContextService
from backend.mesh_store import InMemoryRegistry
import pytest


def test_business_context_persists_objects_and_where_used(tmp_path: Path):
    registry = InMemoryRegistry()
    service = BusinessContextService(tmp_path, registry=registry)
    outcome = service.upsert({
        "nodes": [
            {"id": "part:wheel", "type": "Part", "name": "Wheel", "ontology_class": "ex:Part", "source_artifact": "step:assembly.stp"},
            {"id": "assembly:bike", "type": "Assembly", "name": "Bike", "ontology_class": "ex:Assembly"},
        ],
        "relationships": [{"source": "assembly:bike", "target": "part:wheel", "type": "HAS_PART"}],
    })

    assert outcome["context"]["node_count"] == 2
    assert service.get("assembly:bike")["neighbors"][0]["id"] == "part:wheel"
    assert service.where_used("part:wheel")["used_by"][0]["type"] == "HAS_PART"
    assert BusinessContextService(tmp_path, registry=registry).search("Wheel")["results"]


def test_failed_relationship_does_not_mutate_context(tmp_path):
    registry = InMemoryRegistry()
    service = BusinessContextService(tmp_path, registry=registry)
    with pytest.raises(ValueError):
        service.upsert({"nodes": [{"id": "part:a"}],
                        "edges": [{"source": "part:a", "target": "part:missing"}]})
    assert not service.graph.has_node("part:a")
    assert registry.get("context_graph") is None


def test_stale_writer_preserves_other_writer_data(tmp_path):
    registry = InMemoryRegistry()
    first = BusinessContextService(tmp_path, registry=registry)
    second = BusinessContextService(tmp_path, registry=registry)
    second.summary()
    first.upsert({"nodes": [{"id": "part:a"}]})
    second.upsert({"nodes": [{"id": "part:b"}]})
    fresh = BusinessContextService(tmp_path, registry=registry)
    assert fresh.summary()["node_count"] == 2


def test_failed_persistence_does_not_publish_staged_graph(tmp_path, monkeypatch):
    registry = InMemoryRegistry()
    service = BusinessContextService(tmp_path, registry=registry)
    service.upsert({"nodes": [{"id": "part:a"}]})
    def fail(*args):
        raise RuntimeError("database unavailable")
    monkeypatch.setattr(registry, "put", fail)
    with pytest.raises(RuntimeError):
        service.upsert({"nodes": [{"id": "part:b"}]})
    assert not service.graph.has_node("part:b")


def test_policy_exceptions_fail_closed(tmp_path):
    from backend.ontology_service.intelligence import SemanticIntelligence
    intelligence = SemanticIntelligence(tmp_path, registry=InMemoryRegistry())
    with pytest.raises(ValueError, match="caller overrides"):
        intelligence.evaluate_policies({}, ["mandatory-policy"])
