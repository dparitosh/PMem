import asyncio
from unittest.mock import AsyncMock

import pytest

from backend.agentic_service.answerability import assess
from backend.agentic_service.companion import KnowledgeCompanion


@pytest.mark.parametrize('question', ['How many parts failed inspection?', 'Calculate requirement coverage percentage',
                                    'What is the average mass?', 'Compute total number of parts'])
def test_calculation_never_uses_retrieved_samples(question, monkeypatch):
    monkeypatch.setenv('COMPANION_LLM_ENABLED', 'true')
    token = AsyncMock()
    result = asyncio.run(KnowledgeCompanion().ask(question, headers={}, on_token=token))
    assert result['answerable'] is False
    assert result['status'] == 'unsupported_calculation'
    assert result['retrieval']['calculation_executed'] is False
    assert result['generation']['status'] == 'not_requested'
    token.assert_awaited_once_with(result['response'])


def test_no_rows_and_source_references_do_not_verify_ownership():
    assert assess('Which parts have PMI?', [{'evidence_type': 'business_answer', 'intent': 'parts_with_pmi', 'rows': []}])['answerable'] is False
    reference = {'evidence_type': 'business_answer', 'intent': 'parts_with_pmi', 'rows': [{'association_status': 'source_reference'}]}
    assert assess('Which parts have PMI?', [reference])['status'] == 'unverified_association'
    reference['rows'] = [{'association_status': 'recorded_association'}]
    assert assess('Which parts have PMI?', [reference])['answerable'] is True


@pytest.mark.parametrize('rows', [[], [{'association_status': 'source_reference'}]])
def test_unverified_business_lookup_never_calls_model(monkeypatch, rows):
    from backend.agentic_service import companion_context, local_llm
    monkeypatch.setenv('COMPANION_LLM_ENABLED', 'true')
    monkeypatch.setattr(companion_context, 'semantic_context', AsyncMock(return_value=None))
    monkeypatch.setattr(companion_context, 'mapping_context', AsyncMock(return_value={'status': 'not_requested', 'evidence': []}))
    monkeypatch.setattr(companion_context, 'document_context', AsyncMock(return_value={'status': 'available', 'evidence': []}))
    monkeypatch.setattr(companion_context, 'plm_context', AsyncMock(return_value={
        'evidence_type': 'business_answer', 'resource_id': 'business:parts', 'source': 'graph-service',
        'intent': 'parts_with_pmi', 'rows': rows, 'coverage': {}}))
    model = AsyncMock()
    monkeypatch.setattr(local_llm, 'summarize', model)
    result = asyncio.run(KnowledgeCompanion().ask('Which parts have PMI?', headers={}))
    assert result['answerable'] is False
    assert result['retrieval']['answerability']['answerable'] is False
    assert result['evidence']
    model.assert_not_awaited()


@pytest.mark.parametrize('question', ['Explain the total number property', 'Describe the KPI definition',
                                    'Define average mass', 'Explain percentage coverage',
                                    'Find requirement-to-model links', 'Show quality evidence'])
def test_descriptive_questions_remain_supported(question):
    assert assess(question, [])['answerable'] is True


@pytest.mark.parametrize('question', ['Explain this product and calculate its average mass',
    'What is the sum of component weights?', 'What is the median diameter?', 'What is the ratio of rejected parts?'])
def test_adversarial_calculation_requests_are_not_context_answers(question):
    assert assess(question, [])['status'] == 'unsupported_calculation'


def test_percentage_definition_is_not_a_calculation():
    assert assess('What percentage means in this ontology?', [])['answerable'] is True


@pytest.mark.parametrize('question', ['Is the selected requirement satisfied?', 'Explain whether this part is interchangeable'])
def test_judgments_require_verification_evidence(question):
    assert assess(question, [{'evidence_type': 'graph_resource', 'label': 'Requirement'}])['status'] == 'unsupported_judgment'


@pytest.mark.parametrize('status', ['unknown', None, 'source_reference', 'verified'])
def test_unrecognized_ownership_and_unrelated_records_cannot_pass(status):
    evidence = [{'evidence_type': 'business_answer', 'intent': 'parts_with_pmi', 'rows': [{'association_status': status}]},
                {'evidence_type': 'business_answer', 'intent': 'product_assembly', 'rows': [{'name': 'Part A'}]}]
    assert assess('Which parts have PMI?', evidence)['answerable'] is False


def test_selected_record_context_survives_unsupported_calculation(monkeypatch):
    from backend.agentic_service import selected_record
    retained = {'status': 'grounded', 'answerable': True, 'response': 'Recorded run status: completed',
                'evidence': [{'resource_id': 'run:one'}], 'sources': ['owning-service'],
                'generation': {'status': 'not_requested'}}
    monkeypatch.setattr(selected_record, 'answer', AsyncMock(return_value=retained))
    result = asyncio.run(KnowledgeCompanion().ask('Calculate average mass', headers={}, run_id='one'))
    assert result['answerable'] is False
    assert result['evidence'] == [{'resource_id': 'run:one'}]
    assert 'Recorded run status: completed' in result['response']


def test_semantic_context_cannot_override_calculation_limit(monkeypatch):
    from backend.agentic_service import companion_context
    monkeypatch.setattr(companion_context, 'semantic_context', AsyncMock(return_value={
        'status': 'grounded', 'answerable': True, 'response': 'Recorded vocabulary definitions',
        'evidence': [{'resource_id': 'foundation'}], 'sources': ['ontology-service']}))
    result = asyncio.run(KnowledgeCompanion().ask('Calculate average mass using the embedded foundation', headers={}))
    assert result['status'] == 'unsupported_calculation'
    assert result['answerable'] is False
    assert result['evidence'] == [{'resource_id': 'foundation'}]
    assert 'Recorded vocabulary definitions' in result['response']
