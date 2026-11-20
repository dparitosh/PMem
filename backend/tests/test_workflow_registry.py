from backend.Services.workflow_registry import WORKFLOW_REGISTRY, get_workflow_by_id, get_workflow_map, get_workflow_options


def test_workflow_registry_has_unique_ids_and_labels():
    ids = [workflow["id"] for workflow in WORKFLOW_REGISTRY]
    labels = [workflow["label"] for workflow in WORKFLOW_REGISTRY]

    assert len(ids) == len(set(ids))
    assert len(labels) == len(set(labels))
    assert all(workflow["label"] for workflow in WORKFLOW_REGISTRY)
    assert all(workflow["category"] for workflow in WORKFLOW_REGISTRY)
    assert all(workflow["execution_surface"] in {"upload", "artifact"} for workflow in WORKFLOW_REGISTRY)
    upload_ids = {workflow["id"] for workflow in WORKFLOW_REGISTRY if workflow["execution_surface"] == "upload"}
    assert {"instance.import", "ontology.create", "document.unstructured", "architecture.archimate"}.issubset(upload_ids)
    assert "ReqIF" in get_workflow_by_id("instance.import")["inputs"]
    assert all(workflow["execution_surface"] == "artifact" for workflow in WORKFLOW_REGISTRY if workflow["id"] not in upload_ids)


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


def test_runtime_options_expose_canonical_capabilities_for_every_workflow():
    for option in get_workflow_options():
        canonical = get_workflow_by_id(option['id'])
        for field in ('inputs', 'outputs', 'writes_to_neo4j', 'retains_artifacts'):
            assert option[field] == canonical[field]


def test_frontend_fallback_covers_canonical_workflow_ids():
    import re
    from pathlib import Path
    source = Path('frontend/src/workflows/workflowEngine.js').read_text(encoding='utf-8')
    catalog = source.split('export const workflowCatalog = [', 1)[1].split('export const executableWorkflowIds', 1)[0]
    ids = re.findall(r"id: '([^']+)'", catalog)
    assert len(ids) == len(set(ids))
    assert set(ids) == set(get_workflow_map())


def test_three_ingestion_families_preserve_adapter_and_activity_identity():
    families = {'instance.import','ontology.create','document.unstructured'}
    options = get_workflow_options()
    assert {row['family'] for row in options} == families
    roots = {row['id'] for row in options if row['activity']=='ingestion' and row['adapter'] is None}
    assert roots == families
    archimate = get_workflow_by_id('architecture.archimate')
    assert archimate['family']=='instance.import' and archimate['adapter']=='archimate'
    assert archimate['execution_surface']=='upload'
    assert get_workflow_by_id('instance.link')['activity']=='alignment'
    assert get_workflow_by_id('ontology.merge')['activity']=='merge'
    for row in options:
        assert row['family']==get_workflow_by_id(row['id'])['family']
