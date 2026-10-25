from datetime import datetime, timezone
import pytest
from backend.agentic_service.context_envelope import assemble, public


def envelope(**changes):
    values = dict(owner='server-owner', run_id='run', purpose='read_goal',
                  context={'ontology_id':'selected', 'password':'never-copy'},
                  deadline_at=datetime.now(timezone.utc).isoformat())
    return assemble(**{**values, **changes})


def test_projection_retains_scope_without_private_context_or_implicit_authority():
    result = envelope()
    assert result['scope'] == {'ontology_id':'selected'}
    assert result['source_revision_status'] == 'unverified'
    assert result['authorization'] == 'owner_service_required'
    assert 'never-copy' not in str(result)
    assert 'server-owner' not in str(public(result))


@pytest.mark.parametrize('changes', [{'owner':''}, {'evidence_bytes':True}, {'evidence_bytes':120001},
    {'deadline_at':'2026-10-24T12:00:00'}, {'context':{'source_ontology_ids':'bad'}}])
def test_invalid_context_is_rejected(changes):
    with pytest.raises(ValueError): envelope(**changes)


@pytest.mark.parametrize('field,value', [('owner','other'), ('run_id','other'),
    ('deadline_at','2026-10-25T12:00:00+00:00')])
def test_resume_rejects_changed_context_binding(field, value):
    from backend.agentic_service.context_envelope import verify
    env=envelope()
    record={'owner':'server-owner', 'run_id':'run', 'deadline_at':env['deadline_at'], 'context_envelope':env}
    record[field]=value
    with pytest.raises(ValueError): verify(record, context={'ontology_id':'selected'}, contract_digest='')


def test_resume_checks_scope_and_preserves_legacy_compatibility():
    from backend.agentic_service.context_envelope import verify
    env=envelope()
    record={'owner':'server-owner','run_id':'run','deadline_at':env['deadline_at'],'context_envelope':env}
    assert verify(record, context={'ontology_id':'selected'}, contract_digest='')
    with pytest.raises(ValueError): verify(record, context={'ontology_id':'different'}, contract_digest='')
    assert verify({}, context={}, contract_digest='') is False
