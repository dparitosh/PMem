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
         patch.object(SemanticWorkflowService, "_read_ontology_file", return_value="ClassA ClassB"), \
         patch.object(SemanticWorkflowService, "_extract_terms", side_effect=[
             [{"term": "InstancePart", "tokens": ["instance", "part"]}],
             [{"term": "ClassPart", "tokens": ["class", "part"]}],
         ]), \
         patch("backend.Services.semantic_workflow_service.WorkflowArtifactService.write_json") as write_json, \
         patch("backend.Services.semantic_workflow_service.WorkflowArtifactService.get_manifest", return_value={"artifacts": []}), \
         patch.object(SemanticWorkflowService, "_new_task", return_value="task-1"):
        result = SemanticWorkflowService.link_instances({
            "ontology_id": "ap242",
            "import_artifact_manifest": {"artifact": "value"},
        })

        assert result["status"] == "completed"
        assert result["result"]["ontology_id"] == "ont-123"
        write_json.assert_called_once()
