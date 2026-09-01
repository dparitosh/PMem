from backend.ingestion_service.profiles import SourceProfileStore
from backend.ontology_service.semantica_adapter import SemanticWorkspace


def _store(tmp_path):
    store = SourceProfileStore()
    store.root = tmp_path
    return store


def test_json_profile_executes_a_batch_with_dotted_mappings(tmp_path):
    store = _store(tmp_path)
    profile = store.save({
        "name": "parts", "mapping": {
            "entity": "Part", "identifier": "identity.code", "records_path": "items",
            "properties": {"identity.code": "partNumber", "description": "description"},
        },
    })

    result = store.normalize_batch(
        profile=profile, filename="parts.json",
        content=b'{"items":[{"identity":{"code":"P-1"},"description":"Bracket"}]}',
    )

    assert result["records_processed"] == 1
    assert result["entities"] == [{"id": "P-1", "type": "Part", "partNumber": "P-1", "description": "Bracket"}]
    assert result["provenance"]["profile_version"] == 1


def test_xml_profile_executes_child_records_and_versions_updates(tmp_path):
    store = _store(tmp_path)
    first = store.save({"profile_id": "requirements", "mapping": {"entity": "Requirement", "identifier": "id", "properties": {"title": "title"}}})
    profile = store.save({"profile_id": "requirements", "mapping": {"entity": "Requirement", "identifier": "id", "properties": {"title": "title"}}})

    result = store.normalize_batch(
        profile=profile, filename="requirements.xml",
        content=b'<Requirements><Requirement id="R-1"><title>Safe stop</title></Requirement><Requirement id="R-2"><title>Audit</title></Requirement></Requirements>',
    )

    assert first["version"] == 1
    assert profile["version"] == 2
    assert [item["id"] for item in result["entities"]] == ["R-1", "R-2"]
    assert result["entities"][0]["title"] == "Safe stop"


def test_semantic_workspace_persists_versions_and_alignments(tmp_path):
    workspace = SemanticWorkspace(root=tmp_path)
    version_id = workspace.store({"name": "Parts", "classes": []})
    workspace.align(source_uri="urn:source:part", target_uri="urn:target:part", predicate="skos:exactMatch")

    restored = SemanticWorkspace(root=tmp_path)

    assert restored.get(version_id)["name"] == "Parts"
    assert restored.alignments[0]["storage"] == "semantic_workspace"
