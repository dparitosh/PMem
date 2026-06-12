from unittest.mock import patch

from backend.Services.semantic_workflow_service import SemanticWorkflowService


def test_resolve_ontology_id_accepts_prefix_and_storage_id():
    with patch("backend.Services.semantic_workflow_service.OntologyUploadManager.get_ontology") as get_ontology, \
         patch("backend.Services.semantic_workflow_service.OntologyUploadManager.list_ontologies") as list_ontologies:
        get_ontology.side_effect = lambda ontology_id: (
            {"status": "success", "metadata": {"ontology_id": ontology_id, "prefix": "ap242"}}
            if ontology_id == "ont-123"
            else {"status": "error", "error": "Ontology not found"}
        )
        list_ontologies.return_value = {
            "status": "success",
            "ontologies": [{"ontology_id": "ont-123", "prefix": "ap242"}],
        }

        assert SemanticWorkflowService._resolve_ontology_id("ont-123") == "ont-123"
        assert SemanticWorkflowService._resolve_ontology_id("ap242") == "ont-123"


def test_instance_link_uses_resolved_prefix_reference():
    with patch.object(SemanticWorkflowService, "_resolve_ontology_id", return_value="ont-123"), \
         patch.object(SemanticWorkflowService, "_ontology_metadata", return_value={
             "ontology_id": "ont-123",
             "prefix": "ap242",
             "original_filename": "ap242.owl",
             "file_path": "D:/tmp/ap242.owl",
         }), \
         patch.object(SemanticWorkflowService, "_load_import_task", return_value={
             "task_id": "import-123",
             "parsed_rows": [{"import_row_key": "row-1", "entity_type": "Part"}],
         }), \
         patch.object(SemanticWorkflowService, "_build_link_candidates", return_value=[]), \
         patch("backend.Services.semantic_workflow_service.WorkflowArtifactService.write_json") as write_json, \
         patch("backend.Services.semantic_workflow_service.WorkflowArtifactService.get_manifest", return_value={"artifacts": []}), \
         patch.object(SemanticWorkflowService, "_new_task", return_value="task-1"):
        result = SemanticWorkflowService.link_instances({
            "ontology_id": "ap242",
            "import_artifact_manifest": {"task_id": "import-123"},
        })

        assert result["status"] == "completed"
        assert result["result"]["ontology_id"] == "ont-123"
        write_json.assert_called_once()


def test_build_link_candidates_prefers_specific_type_match_over_generic_name(monkeypatch):
    rows = [
        {
            "import_row_key": "row-1",
            "name": "Validate Speed",
            "entity_type": "Requirement",
        }
    ]

    monkeypatch.setattr(
        SemanticWorkflowService,
        "AUTO_APPLY_CONFIDENCE",
        0.8,
    )

    def fake_lookup(_prefix):
        return {
            "REQUIREMENT": [
                {
                    "element_id": "class-1",
                    "class_name": "Requirement",
                    "prefix": "mbse",
                    "normalized": "REQUIREMENT",
                    "tokens": ["requirement"],
                    "is_generic": False,
                }
            ],
            "PART": [
                {
                    "element_id": "class-2",
                    "class_name": "Part",
                    "prefix": "mbse",
                    "normalized": "PART",
                    "tokens": ["part"],
                    "is_generic": True,
                }
            ],
        }

    monkeypatch.setattr(
        "backend.Services.semantic_workflow_service.UnifiedDataImportService._load_ontology_class_lookup",
        fake_lookup,
    )

    candidates = SemanticWorkflowService._build_link_candidates(rows, "mbse", "import-1")

    assert len(candidates) == 1
    assert candidates[0]["ontology_term"] == "Requirement"
    assert candidates[0]["selected_for_apply"] is True
    assert candidates[0]["generic_match"] is False


def test_build_link_candidates_filters_generic_name_only_matches(monkeypatch):
    rows = [
        {
            "import_row_key": "row-2",
            "name": "Part",
        }
    ]

    def fake_lookup(_prefix):
        return {
            "PART": [
                {
                    "element_id": "class-2",
                    "class_name": "Part",
                    "prefix": "mbse",
                    "normalized": "PART",
                    "tokens": ["part"],
                    "is_generic": True,
                }
            ]
        }

    monkeypatch.setattr(
        "backend.Services.semantic_workflow_service.UnifiedDataImportService._load_ontology_class_lookup",
        fake_lookup,
    )

    candidates = SemanticWorkflowService._build_link_candidates(rows, "mbse", "import-1")

    assert candidates == []


def test_build_link_candidates_uses_instance_metadata_signals(monkeypatch):
    rows = [{"import_row_key": "row-meta-only"}]

    def fake_lookup(_prefix):
        return {
            "INDUCTIONMOTOR": [
                {
                    "element_id": "class-99",
                    "class_name": "InductionMotor",
                    "prefix": "plmxml",
                    "normalized": "INDUCTIONMOTOR",
                    "tokens": ["induction", "motor"],
                    "is_generic": False,
                }
            ]
        }

    monkeypatch.setattr(
        "backend.Services.semantic_workflow_service.UnifiedDataImportService._load_ontology_class_lookup",
        fake_lookup,
    )

    import_task = {
        "task_id": "import-meta-1",
        "filename": "InductionMotor.xml",
        "file_type": "xml",
        "workflow_id": "instance.import",
        "stats": {
            "ontology_name": "Induction Motor",
            "ontology_prefix": "motor",
            "namespace": "http://example.com/motor#",
        },
    }

    candidates = SemanticWorkflowService._build_link_candidates(rows, "motor", "import-meta-1", import_task=import_task)

    assert len(candidates) == 1
    assert candidates[0]["ontology_term"] == "InductionMotor"
    assert candidates[0]["match_source"].startswith("manifest.")
    assert any(str(source).startswith("manifest.") for source in candidates[0].get("evidence", []))


def test_build_link_candidates_classifies_relationship_rows_to_object_properties(monkeypatch):
    rows = [
        {
            "import_row_key": "rel-1",
            "name": "bearing",
            "href": "#Part",
        }
    ]

    def fake_lookup(_prefix):
        return {
            "BEARING": [
                {
                    "element_id": "class-9",
                    "class_name": "bearing",
                    "prefix": "plmxml",
                    "normalized": "BEARING",
                    "tokens": ["bearing"],
                    "is_generic": False,
                    "target_ontology_type": "Class",
                }
            ]
        }

    monkeypatch.setattr(
        "backend.Services.semantic_workflow_service.UnifiedDataImportService._load_ontology_class_lookup",
        fake_lookup,
    )
    monkeypatch.setattr(
        "backend.Services.semantic_workflow_service.OntologyTaxonomyService.get_reasoning",
        lambda ontology_id: {
            "classes": [],
            "object_properties": [
                {
                    "label": "bearing",
                    "iri": "urn:target:bearing",
                    "domain": [{"label": "Part"}],
                    "range": [{"label": "Part"}],
                }
            ],
            "datatype_properties": [],
            "annotation_properties": [],
            "subclass_edges": [],
        },
    )

    candidates = SemanticWorkflowService._build_link_candidates(rows, "plmxml", "import-rel-1")

    assert len(candidates) == 1
    assert candidates[0]["source_type"] == "Relationship"
    assert candidates[0]["target_ontology_type"] == "ObjectProperty"


def test_merge_ontologies_uses_semantic_structure_instead_of_raw_tokens(monkeypatch):
    monkeypatch.setattr(
        "backend.Services.semantic_workflow_service.SemanticWorkflowService._resolve_ontology_id",
        lambda ontology_id: ontology_id,
    )
    monkeypatch.setattr(
        "backend.Services.semantic_workflow_service.SemanticWorkflowService._ontology_metadata",
        lambda ontology_id: {"ontology_id": ontology_id, "original_filename": f"{ontology_id}.owl"},
    )
    monkeypatch.setattr(
        "backend.Services.semantic_workflow_service.SemanticWorkflowService._new_task",
        lambda workflow_id, source_filename="": "merge-task",
    )

    captured = {}

    def fake_write_json(task_id, folder, filename, payload, artifact_type):
        captured["task_id"] = task_id
        captured["payload"] = payload

    monkeypatch.setattr(
        "backend.Services.semantic_workflow_service.WorkflowArtifactService.write_json",
        fake_write_json,
    )
    monkeypatch.setattr(
        "backend.Services.semantic_workflow_service.WorkflowArtifactService.get_manifest",
        lambda task_id: {"task_id": task_id},
    )

    def fake_reasoning(ontology_id):
        if ontology_id == "source":
            return {
                "classes": [
                    {"label": "Requirement", "iri": "urn:source:Requirement"},
                    {"label": "Part", "iri": "urn:source:Part"},
                ],
                "object_properties": [
                    {
                        "label": "satisfies",
                        "iri": "urn:source:satisfies",
                        "domain": [{"label": "Requirement"}],
                        "range": [{"label": "Part"}],
                    }
                ],
                "datatype_properties": [],
                "subclass_edges": [{"source_label": "Requirement", "target_label": "Part"}],
            }
        return {
            "classes": [
                {"label": "Requirement", "iri": "urn:target:Requirement"},
            ],
            "object_properties": [
                {
                    "label": "satisfies",
                    "iri": "urn:target:satisfies",
                    "domain": [{"label": "Requirement"}],
                    "range": [{"label": "Document"}],
                }
            ],
            "datatype_properties": [],
            "subclass_edges": [],
        }

    monkeypatch.setattr(
        "backend.Services.semantic_workflow_service.OntologyTaxonomyService.get_reasoning",
        fake_reasoning,
    )

    result = SemanticWorkflowService.merge_ontologies(
        {"source_ontology_id": "source", "target_ontology_id": "target"}
    )

    summary = result["result"]["summary"]
    assert summary["overlap_count"] == 2
    assert summary["addition_count"] == 1
    assert summary["conflict_count"] == 1
    assert summary["subclass_gap_count"] == 1
    assert captured["payload"]["overlaps"][0]["match_basis"] == "label"
