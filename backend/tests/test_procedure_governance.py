from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from backend.agentic_service.catalog_contract import validate_procedure_governance
from backend.agentic_service import router


@pytest.mark.parametrize('value', [None, {}, {'status':'approved','version':'1.0.0'},
    {'status':'approved','version':'latest','approved_by':'reviewer','evaluation_sha256':'a'*64}])
def test_invalid_promotion_metadata_rejected(value):
    with pytest.raises(ValueError): validate_procedure_governance(value)


def test_approved_procedure_requires_version_review_identity_and_evaluation_digest():
    validate_procedure_governance({'status':'approved','version':'1.0.0','approved_by':'reviewer','evaluation_sha256':'a'*64})


@pytest.mark.parametrize('status',['proposed','retired'])
def test_nonapproved_procedure_cannot_be_planned(monkeypatch,status):
    monkeypatch.setattr(router,'catalog',SimpleNamespace(item=lambda *a:{'id':'procedure','governance':{'version':'1.0.0','status':status},'steps':[]}))
    with pytest.raises(HTTPException) as failure: router.workflow_plan({'workflow_id':'procedure'})
    assert failure.value.status_code==422
    assert 'proposed or retired' in failure.value.detail
