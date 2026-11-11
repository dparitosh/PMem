"""Regression coverage for distinct record, definition and execution identities."""
from backend.oslc_service.change_control import normalize, SUMMARY_FIELDS
from backend.agentic_service.page_tasks import summary, page_binding

def test_publication_jobs_for_one_ontology_have_distinct_record_keys():
    first=normalize('publications',{'ontology_id':'motor','job_id':'publish-1','status':'queued'})
    second=normalize('publications',{'ontology_id':'motor','job_id':'publish-2','status':'failed'})
    assert first['record_key']!=second['record_key']
    assert first['identifier']=='publish-1'
    assert first['identifier_label']=='Publication job ID'
    assert first['evidence']['ontology_id']=='motor'
    assert first['workspace']=='#/ontology?target=motor'

def test_pipeline_definition_name_version_and_execution_remain_separate():
    record=normalize('pipeline',{'run_id':'run-1','job_id':'validate','job_name':'Validate semantic source','job_version':'2','status':'completed'})
    assert record['title']=='Validate semantic source'
    assert record['identifier']=='run-1' and record['identifier_label']=='Run ID'
    assert record['evidence']['job_id']=='validate' and record['evidence']['job_version']=='2'
    assert record['workspace']=='#/data-flow/run-1'
    assert 'job_version' in SUMMARY_FIELDS and 'job_name' in SUMMARY_FIELDS

def test_legacy_publication_fallback_is_stable_without_rewriting_records():
    record={'ontology_id':'motor','artifact_sha256':'digest-1','status':'published'}
    assert normalize('publications',record)['record_key']=='publications:motor@digest-1'
    assert record=={'ontology_id':'motor','artifact_sha256':'digest-1','status':'published'}

def test_page_task_keeps_workflow_name_and_definition_id_separate_from_run():
    row=summary({'run_id':'run-1','workflow_id':'definition-1','workflow_name':'Review mapping'},'workflow')
    assert row['title']=='Review mapping' and row['workflow_id']=='definition-1' and row['run_id']=='run-1'
    assert page_binding('owner',{'page':'change-control'})['page_context']['page']=='change-control'

def test_collection_preserves_separate_publication_jobs_for_one_ontology():
    from backend.oslc_service.change_control import collect
    class Registry:
        def page(self, **options):
            return 2, [{'ontology_id':'motor','job_id':key,'status':'queued'} for key in ('publish-1','publish-2')]
    result=collect('publications',registry_factory=lambda namespace: Registry())
    assert len(result['records'])==2
    assert len({row['record_key'] for row in result['records']})==2
    assert result['coverage'][0]['total']==2 and not result['partial']
