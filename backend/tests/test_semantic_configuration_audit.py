"""Regression coverage for the four configuration/TRS audit fixes."""
from unittest.mock import patch
import pytest
from backend.data_pipeline_service import semantic_configuration as configuration, run_records
from backend.tests import test_semantic_configuration as configuration_fixtures


@pytest.fixture
def setup_configuration():
    context=configuration_fixtures.ConfigurationTests()
    context.setUp()
    try:
        yield context
    finally:
        context.doCleanups()


def test_successful_refresh_review_is_a_completed_workflow(setup_configuration):
    context=setup_configuration
    context.resolve.return_value={'revision':2,'version':'1.0.0'}
    result=configuration.execute_review(None,{'dataset_id':context.dataset},correlation_id='audit')
    record={'run_id':'audit-run','job_id':'source-review','job_version':'1.0.0','job_type':'semantic-source-review'}
    with patch.object(run_records,'ArtifactStore') as artifacts, patch.object(run_records,'replay_payload',return_value={}), patch.object(run_records,'_persist_execution',side_effect=lambda old,new:new):
        artifacts.return_value.ingest_bytes.return_value={'artifact_id':'sha256:result'}
        retained=run_records._complete_with_evidence(record,result)
    assert retained['status']=='completed'
    assert retained['output_manifest']['assessment_status']=='refresh_required'


def test_replayed_preparation_retains_its_first_configuration(setup_configuration):
    context=setup_configuration
    payload={'source_id':context.selection['source_id'],'artifact_id':context.selection['artifact_id']}
    definition={'job_id':'prepare','version':'1.0.0','job_type':'rdf-semantic-materialize','input_contract':'registered-rdf-source-v1'}
    with patch.object(run_records,'ArtifactStore',return_value=context.artifacts), patch.object(run_records,'store') as runs:
        runs.put.side_effect=lambda key,value:value
        retained=run_records.start.__wrapped__(definition,payload,correlation_id='audit')
        original=retained['input_manifest']['configuration_id']
        context.resolve.return_value={'revision':2,'version':'1.0.0'}
        replay_payload=run_records.replay_payload(retained)
        replay,_,_=configuration.preparation_configuration(replay_payload)
    assert replay['configuration_id']==original
    assert replay['selections'][0]['source_version']['revision']==1



def test_analysis_product_draft_retains_configuration_context():
    record={'run_id':'audit-run','job_id':'analysis','job_version':'1.0.0','job_type':'semantic-dataset-analysis'}
    result={'status':'completed','configuration_id':'a'*64,'data_product_draft':{
        'contract':'semantic-analysis-product-v1','configuration_id':'a'*64,
        'configuration_context':'/oslc/lifecycle/analytics-baselines/'+'a'*64,'sources':[]}}
    with patch.object(run_records,'ArtifactStore') as artifacts, patch.object(run_records,'replay_payload',return_value={}), patch.object(run_records,'_persist_execution',side_effect=lambda old,new:new):
        artifacts.return_value.ingest_bytes.return_value={'artifact_id':'sha256:result'}
        retained=run_records._complete_with_evidence(record,result)
    assert retained['output_manifest']['data_product_draft']['configuration_id']=='a'*64
    assert retained['output_manifest']['data_product_draft']['configuration_context'].endswith('a'*64)


def test_legacy_preparation_without_a_binding_fails_closed(setup_configuration):
    context=setup_configuration
    import json
    artifact=context.artifacts.ingest_bytes(json.dumps(context.selection).encode(),filename='legacy-input.json')
    record={'run_id':'legacy','job_type':'rdf-semantic-materialize',
            'input_manifest':{'raw_payload_artifact_id':artifact['artifact_id']}}
    with patch.object(run_records,'ArtifactStore',return_value=context.artifacts):
        with pytest.raises(ValueError,match='no verified baseline binding'):
            run_records.replay_payload(record)


def test_completed_legacy_run_can_recover_its_retained_output_binding(setup_configuration):
    context=setup_configuration
    import json
    artifact=context.artifacts.ingest_bytes(json.dumps(context.selection).encode(),filename='legacy-input.json')
    record={'run_id':'legacy','job_type':'rdf-semantic-materialize',
            'input_manifest':{'raw_payload_artifact_id':artifact['artifact_id']},
            'output_manifest':{'configuration_id':context.baseline['configuration_id']}}
    with patch.object(run_records,'ArtifactStore',return_value=context.artifacts):
        replay=run_records.replay_payload(record)
    assert replay['configuration_id']==context.baseline['configuration_id']


@pytest.mark.parametrize('claimed',[False,True])
def test_both_dispatch_paths_use_retained_input_not_the_mutable_caller(claimed):
    from contextlib import nullcontext
    from unittest.mock import MagicMock
    from backend.data_pipeline_service import execution
    definition={'job_type':'rdf-semantic-materialize'}
    run={'run_id':'test','executed_by':'verified-actor'}
    pinned={'configuration_id':'a'*64,'source_id':'catalog:parts:1','artifact_id':'sha256:owned'}
    with patch.object(execution,'execution_context',return_value=MagicMock()), \
         patch.object(execution,'operation_scope',return_value=nullcontext()), \
         patch.object(execution.runner,'execution_scope',return_value=nullcontext()), \
         patch.object(execution,'guarded_execution',return_value=nullcontext()), \
         patch.object(execution.run_records,'replay_payload',return_value=pinned), \
         patch.object(execution.run_records,'complete',return_value={}), \
         patch.object(execution.handler_registry,'get') as get:
        get.return_value.execute.return_value={'status':'completed'}
        if claimed:
            execution.execute_claimed_job(definition,{'configuration_id':'WRONG'},run)
        else:
            execution.execute_immediate_job(definition,{'configuration_id':'WRONG'},run)
        assert get.return_value.execute.call_args.args[1]=={**pinned,'execution_actor':'verified-actor'}
