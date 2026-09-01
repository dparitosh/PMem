from pathlib import Path

from backend.ontology_service.business_context import BusinessContextService


def test_business_context_persists_objects_and_where_used(tmp_path: Path):
    service = BusinessContextService(tmp_path)
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
    assert BusinessContextService(tmp_path).search("Wheel")["results"]
