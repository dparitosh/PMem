import json
from unittest.mock import patch,Mock
from types import SimpleNamespace
import pytest
from backend.depo_platform.graph_data_client import GraphDataClient


def page(offset,following,revision='a'*64,count=5000):
    return {'scope':'model','offset':offset,'next_offset':following,'revision':revision,
        'terms':[{'element_id':str(i),'kind':'Class','name':'Part'+str(i)} for i in range(offset,offset+count)]}


def read(pages):
    responses=[SimpleNamespace(content=json.dumps(item).encode(),raise_for_status=lambda:None) for item in pages]
    with patch('backend.depo_platform.peer_http.peer_response',side_effect=responses),patch('backend.depo_platform.graph_data_client.service_bearer_headers',return_value={}):
        return GraphDataClient().mapping_terms('model')


def test_large_lookup_returns_all_pages_not_the_first_ten_thousand():
    terms=read([page(0,5000),page(5000,10000),page(10000,None,count=27)])
    assert len(terms)==10027 and terms[-1]['element_id']=='10026'


@pytest.mark.parametrize('change',[{'revision':'b'*64},{'scope':'different'},{'offset':0},{'next_offset':10001}])
def test_changed_revision_scope_or_continuation_rejects_partial_lookup(change):
    second={**page(5000,10000),**change}
    with pytest.raises(RuntimeError):read([page(0,5000),second])


def test_duplicate_target_and_unversioned_multi_page_are_rejected():
    second=page(5000,None,count=1);second['terms'][0]['element_id']='0'
    with pytest.raises(RuntimeError,match='repeated'):read([page(0,5000),second])
    with pytest.raises(RuntimeError,match='version-bound'):read([page(0,5000,revision=None)])


def test_legacy_small_complete_peer_remains_compatible():
    assert len(read([{'terms':[{'element_id':'legacy','name':'Part','kind':'Class'}]}]))==1


def test_publisher_pagination_is_bounded_and_revision_tagged(monkeypatch):
    import ast
    from pathlib import Path
    from contextlib import nullcontext
    from backend.graph_service import query_repository
    tree=ast.parse(Path('backend/graph_service/neo4j_publisher.py').read_text())
    owner=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Neo4jPublisher')
    method=next(n for n in owner.body if isinstance(n,ast.FunctionDef) and n.name=='mapping_terms')
    namespace={'Any':object,'cypher':query_repository}
    wrapper=ast.ClassDef(name='Publisher',bases=[],keywords=[],body=[method],decorator_list=[])
    exec(compile(ast.fix_missing_locations(ast.Module(body=[wrapper],type_ignores=[])),'publisher','exec'),namespace)
    from backend.depo_platform import graph_access
    monkeypatch.setattr(graph_access,'projection_access',nullcontext)
    publisher=namespace['Publisher']();publisher._session_rows=Mock(side_effect=[[{'id':'published','artifact':'a'*64}],[{'name':'one'},{'name':'two'}]])
    result=publisher.mapping_terms('model',offset=0,limit=1)
    assert result['terms']==[{'name':'one'}] and result['next_offset']==1 and len(result['revision'])==64
    assert 'SKIP toInteger($offset)' in publisher._session_rows.call_args.args[0]
    assert publisher._session_rows.call_args.kwargs['read_limit']==2
