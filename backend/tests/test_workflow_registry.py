from backend.Services.workflow_registry import WORKFLOW_REGISTRY, get_workflow_by_id, get_workflow_map, get_workflow_options


def test_workflow_registry_has_unique_ids_and_labels():
    ids = [workflow["id"] for workflow in WORKFLOW_REGISTRY]
    labels = [workflow["label"] for workflow in WORKFLOW_REGISTRY]

    assert len(ids) == len(set(ids))
    assert len(labels) == len(set(labels))
    assert all(workflow["label"] for workflow in WORKFLOW_REGISTRY)
    assert all(workflow["category"] for workflow in WORKFLOW_REGISTRY)
    assert all(workflow["execution_surface"] in {"upload", "artifact"} for workflow in WORKFLOW_REGISTRY)
    assert sum(1 for workflow in WORKFLOW_REGISTRY if workflow["execution_surface"] == "upload") == 2
    assert sum(1 for workflow in WORKFLOW_REGISTRY if workflow["execution_surface"] == "artifact") == 6


def test_workflow_options_include_display_metadata():
    options = get_workflow_options()

    assert len(options) == len(WORKFLOW_REGISTRY)
    assert all(option["label"] for option in options)
    assert all(option["title"] for option in options)
    assert all(option["category"] for option in options)
    assert all(option["execution_surface"] in {"upload", "artifact"} for option in options)
    assert {option["id"] for option in options} == {workflow["id"] for workflow in WORKFLOW_REGISTRY}


def test_workflow_lookup_helpers_are_consistent():
    workflow = get_workflow_by_id("ontology.validate")
    workflow_map = get_workflow_map()

    assert workflow is not None
    assert workflow["id"] == "ontology.validate"
    assert workflow_map["ontology.validate"]["label"] == workflow["label"]
