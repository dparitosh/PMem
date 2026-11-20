from unittest.mock import MagicMock
import pytest
from backend.graph_service.source_revision import source_revision

def publisher(rows):
    owner=MagicMock();tx=owner._driver.return_value.__enter__.return_value.session.return_value.__enter__.return_value.begin_transaction.return_value
    tx.run.side_effect=[MagicMock(data=lambda value=value:value) for value in rows]
    return owner,tx

def snapshot(nodes=None,edges=None):
    nodes=nodes or [{'id':'one','labels':['Part'],'properties':{'name':'Shaft','revision':'B'}}]
    return [[{'scope':'selected'}],nodes,edges or []]

def test_fingerprint_preserves_identity_and_changes_with_source_values():
    a,tx=publisher(snapshot());first=source_revision.__wrapped__(a,'one','selected')
    b,_=publisher(snapshot(nodes=[{'id':'one','labels':['Part'],'properties':{'name':'Shaft','revision':'C'}}]));second=source_revision.__wrapped__(b,'one','selected')
    assert first['revision_sha256']!=second['revision_sha256']
    assert first['node_id']=='one' and first['limited'] is False
    assert 'properties' not in first
    tx.commit.assert_called_once()

def test_wrong_scope_fails_before_reading_source_data():
    owner,tx=publisher([[{'scope':'other'}]])
    with pytest.raises(ValueError):source_revision.__wrapped__(owner,'one','selected')
    assert tx.run.call_count==1;tx.rollback.assert_called_once()

def test_oversized_sources_fail_without_truncated_revision():
    owner,tx=publisher(snapshot(nodes=[{'id':str(i)} for i in range(10001)]))
    with pytest.raises(ValueError):source_revision.__wrapped__(owner,'one','selected')
    tx.rollback.assert_called_once();tx.commit.assert_not_called()
