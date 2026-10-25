from unittest.mock import AsyncMock
import pytest
from backend.agentic_service import source_revisions as revisions


def receipt(**changes):
    return {'ontology_id':'selected', 'artifact_sha256':'a'*64, 'lifecycle_status':'approved', 'status':'registered', **changes}


@pytest.mark.asyncio
async def test_authoritative_receipt_uses_owner_api_and_projects_metadata(monkeypatch):
    read=AsyncMock(return_value=({**receipt(), 'password':'private'}, 'owner'))
    monkeypatch.setattr(revisions, '_read_json', read)
    assert await revisions.capture({'ontology_id':'selected'}, {'Authorization':'Bearer fixture'}) == [receipt()]
    assert read.call_args.args[2] == '/ontologies/selected/revision'


@pytest.mark.asyncio
@pytest.mark.parametrize('changes', [{'artifact_sha256':'bad'}, {'ontology_id':'other'}, {'status':'superseded'}, {'lifecycle_status':'retired'}])
async def test_invalid_or_retired_revision_rejected(monkeypatch, changes):
    monkeypatch.setattr(revisions, '_read_json', AsyncMock(return_value=(receipt(**changes), 'owner')))
    with pytest.raises(ValueError): await revisions.capture({'ontology_id':'selected'}, {})


@pytest.mark.asyncio
async def test_changed_revision_requires_new_review_and_legacy_remains_compatible(monkeypatch):
    monkeypatch.setattr(revisions, 'capture', AsyncMock(return_value=[receipt(artifact_sha256='b'*64)]))
    with pytest.raises(ValueError):
        await revisions.verify({'scope':{'ontology_id':'selected'}, 'source_revisions':[receipt()]}, {})
    assert await revisions.verify({}, {}) is False


def test_source_target_ids_are_deduplicated_and_bounded():
    assert revisions.ontology_ids({'ontology_id':'a', 'source_ontology_ids':['a','b']}) == ['a','b']
    with pytest.raises(ValueError): revisions.ontology_ids({'source_ontology_ids':[str(i) for i in range(11)]})



def test_revision_endpoint_reads_digest_and_lifecycle_under_owner_lock():
    import ast
    from pathlib import Path
    from types import SimpleNamespace
    from fastapi import HTTPException
    tree=ast.parse(Path('backend/ontology_service/router.py').read_text(encoding='utf-8'))
    node=next(item for item in tree.body if getattr(item,'name','')=='ontology_revision')
    node.decorator_list=[]
    events=[]
    def locked(identifier, callback):
        events.append('lock')
        result=callback()
        events.append('unlock')
        return result
    ns={'HTTPException':HTTPException, 'catalog':SimpleNamespace(
        with_publication_lock=locked, get=lambda i:{'lifecycle_status':'approved','status':'registered'},
        artifact_digest=lambda i:events.append('digest') or 'a'*64)}
    exec(compile(ast.Module(body=[node],type_ignores=[]),'revision.py','exec'),ns)
    assert ns['ontology_revision']('selected') == receipt()
    assert events == ['lock','digest','unlock']



@pytest.mark.asyncio
async def test_revision_set_has_one_total_deadline(monkeypatch):
    import asyncio
    monkeypatch.setattr(revisions, 'bounded_timeout_seconds', lambda *a, **kw: 0.001)
    async def slow(*args):
        await asyncio.sleep(1)
        return receipt(), 'owner'
    monkeypatch.setattr(revisions, '_read_json', slow)
    with pytest.raises(TimeoutError): await revisions.capture({'ontology_id':'selected'}, {})
