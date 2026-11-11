from pathlib import Path

from backend.ontology_service.intelligence import SemanticIntelligence
from backend.depo_platform.decision_policy import decision


class MemoryStore:
    def __init__(self):
        self.data = {}

    def get(self, key):
        return self.data.get(key)

    def put(self, key, value):
        self.data[key] = value

    def prefix_items(self, prefix, limit=1000):
        return {k: v for k, v in self.data.items() if k.startswith(prefix)}


def test_assessment_evidence_is_retained_in_the_injected_store(tmp_path: Path):
    registry, evidence = MemoryStore(), MemoryStore()
    service = SemanticIntelligence(tmp_path, registry, evidence_store=evidence)
    report = service.evaluate_decisions('ontology_merge', [decision(artifact_sha256='abc', source_ontology_ids=['a'], selected_mappings=[])])
    assert report['status'] == 'not_configured'
    assert report['blocking'] is False
    assert report['assessment_id'] in evidence.data
    assert evidence.data[report['assessment_id']]['operation'] == 'ontology_merge'


def test_default_evidence_store_still_targets_postgres(tmp_path: Path, monkeypatch):
    import backend.ontology_service.intelligence as module
    created = []

    class Recorder(MemoryStore):
        def __init__(self, name):
            super().__init__()
            created.append(name)

    monkeypatch.setattr(module, 'PostgresRegistry', Recorder)
    service = SemanticIntelligence(tmp_path, MemoryStore())
    service.evaluate_decisions('ontology_merge', [decision(artifact_sha256='abc', source_ontology_ids=['a'], selected_mappings=[])])
    assert 'semantic_decision_assessments' in created
