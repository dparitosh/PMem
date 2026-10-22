from contextlib import nullcontext
import pytest
from backend.graph_service import explorer_search as search


@pytest.fixture
def source(monkeypatch):
    import backend.depo_platform.graph_access as access
    monkeypatch.setattr(access,'projection_access',lambda:nullcontext())
    calls=[]
    def rows(query,**params):
        calls.append((query,params))
        a={'elementId':'a','label':'Bolt','properties':[['material','Titanium']]}
        b={'elementId':'b','label':'Assembly','properties':[]}
        if query==search.NODE_QUERY:return [{'node':a}]
        if query==search.EDGE_QUERY:return [{'source':a,'target':b,'edge':{'elementId':'r','start':'a','end':'b','type':'PART_OF','properties':[['position','Front']]}}]
        return []
    monkeypatch.setattr(search.publisher,'_session_rows',rows)
    return calls


def test_search_is_parameterized_scoped_bounded_and_keeps_relationship_endpoints(source):
    result=search.search("' OR true //",scope='selected',limit=500)
    assert len(result['nodes'])==2 and result['relationships'][0]['properties']=={'position':'Front'}
    assert result['view']['limit']==200
    assert all(params['_timeout_seconds']<=30 for _,params in source)
    assert source[0][1]['scope']=='selected' and source[0][1]['needle']=="' or true //"
    assert "' or true //" not in source[0][0]


def test_query_includes_keys_values_arrays_and_excludes_unpublished_and_private_data():
    assert 'keys(n)' in search.NODE_QUERY and 'LIST<ANY>' in search.NODE_QUERY
    assert 'type(r)' in search.EDGE_QUERY and 'keys(r)' in search.EDGE_QUERY
    assert 'StagedOntologyResource' in search.EDGE_QUERY and 'RetainedOntologyIdentity' in search.NODE_QUERY
    assert 'token' in search.PRIVATE_KEYS and 'authorization' in search.PRIVATE_KEYS


@pytest.mark.parametrize('value',['','*','x'*501])
def test_invalid_queries_never_reach_graph(source,value):
    with pytest.raises(ValueError):search.search(value)
    assert not source
