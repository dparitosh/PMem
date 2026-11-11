from unittest.mock import MagicMock, patch
from backend.agentic_service.context_scope import same_companion_scope
from backend.agentic_service.companion_memory import recall_turns, retrieval_query

def test_explicit_business_identity_can_cross_pages_but_not_versions():
    scope={'ontology':'o','node_id':'n','page':'graph'}
    assert same_companion_scope(scope,{**scope,'page':'data-products'})
    assert not same_companion_scope(scope,{**scope,'node_id':'other'})
    assert not same_companion_scope({'page':'graph'},{'page':'data-products'})
    assert not same_companion_scope({'product_id':'p','product_version':'1'},{'product_id':'p','product_version':'2'})

def test_scoped_query_filters_before_limit_and_is_read_only():
    from backend.agentic_service import router
    cursor=MagicMock();cursor.fetchall.return_value=[({'job_id':'matching'},)]
    registry=MagicMock();registry.namespace='companion';registry._connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value=cursor
    with patch.object(router,'companion_job_store',registry):
        rows=router._session_turns({'owner':'owner','session_id':'s'},6,{'page':'graph','node_id':'n'},True)
    query,args=cursor.execute.call_args.args
    assert "value->>'owner'=%s" in query and "value->'graph_context'->>%s" in query
    assert "answerable" in query and 'LIMIT %s' in query and args[-1]==6
    assert 'node_id' in args and 'page' not in args
    assert cursor.execute.call_args_list[0].args[0]=='SET TRANSACTION READ ONLY'
    assert rows==[{'job_id':'matching'}]

def test_semantica_and_langchain_recall_keep_latest_subject_and_provenance():
    scope={'ontology':'o','node_id':'n','page':'graph'}
    turns=[{'job_id':'new','user_request':'Housing','answerable':True,'graph_context':scope},
           {'job_id':'old','user_request':'PMI for Shaft','answerable':True,'graph_context':scope}]
    from semantica.context.agent_memory import AgentMemory
    original=AgentMemory.retrieve
    with patch.object(AgentMemory,'retrieve',autospec=True,side_effect=original) as retrieve:
        result=recall_turns('its PMI',turns,{**scope,'page':'data-products'})
        assert retrieve.called
    assert result[0]['job_id']=='new'
    assert 'Housing' in retrieval_query('its properties',turns,scope)
    assert recall_turns('PMI',turns,{**scope,'node_id':'other'})==[]


def test_explicit_subject_does_not_inherit_latest_topic():
    scope={'page':'graph'}
    turns=[{'user_request':'Housing','answerable':True,'graph_context':scope}]
    for query in ('more about Shaft', 'Show more requirements for Shaft', 'details about Shaft'):
        assert retrieval_query(query,turns,scope)==query


def test_missing_langchain_uses_scoped_fallback():
    import builtins
    original=builtins.__import__
    def unavailable(name,*args,**kwargs):
        if name=='langchain_core.documents':
            raise ImportError('simulated dependency failure')
        return original(name,*args,**kwargs)
    scope={'page':'graph'}
    turns=[{'user_request':'Housing','answerable':True,'graph_context':scope},
           {'user_request':'Other','answerable':True,'graph_context':{'page':'other'}}]
    with patch('builtins.__import__',side_effect=unavailable):
        assert recall_turns('its properties',turns,scope)==turns[:1]
        assert retrieval_query('its properties',turns,scope)=='Housing its properties'


def test_non_pronoun_recall_honors_semantica_ranking():
    from semantica.context.agent_memory import AgentMemory
    scope={'page':'graph'}
    turns=[{'user_request':'Housing','answerable':True,'graph_context':scope},
           {'user_request':'Shaft','answerable':True,'graph_context':scope}]
    with patch.object(AgentMemory,'retrieve',return_value=[{'metadata':{'index':1}}]):
        assert recall_turns('Shaft',turns,scope)[0]==turns[1]
        assert recall_turns('its properties',turns,scope)[0]==turns[0]
