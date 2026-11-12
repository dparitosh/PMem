"""Bounded memory regression coverage for the supported Companion engine."""
from backend.agentic_service.companion_memory import recall_turns,retrieval_query


def test_chat_memory_trims_to_the_scoped_recall_limit(monkeypatch):
    from semantica.context.agent_memory import AgentMemory
    monkeypatch.setattr(AgentMemory,'retrieve',lambda *args,**kwargs:[])
    scope={'ontology':'version-1','node_id':'part-1'}
    turns=[{'job_id':str(i),'user_request':'Part '+str(i),'graph_context':scope,'answerable':True} for i in range(80)]
    selected=recall_turns('its properties',turns,scope,limit=6)
    assert len(selected)==6 and [x['job_id'] for x in selected]==[str(i) for i in range(6)]


def test_failed_and_different_scope_turns_do_not_consume_the_recall_limit(monkeypatch):
    from semantica.context.agent_memory import AgentMemory
    monkeypatch.setattr(AgentMemory,'retrieve',lambda *args,**kwargs:[])
    scope={'ontology':'version-1','node_id':'part-1'}
    failed=[{'user_request':'Failed answer','graph_context':scope,'status':'failed'} for _ in range(60)]
    other=[{'user_request':'Different version','graph_context':{**scope,'ontology':'version-2'}} for _ in range(60)]
    retained={'job_id':'good','user_request':'Housing','graph_context':scope,'answerable':True}
    assert recall_turns('its properties',failed+other+[retained],scope)==[retained]


def test_previous_version_does_not_supply_the_current_subject():
    scope={'ontology':'version-2','node_id':'part-1'}
    turns=[{'user_request':'Housing','answerable':True,'graph_context':{**scope,'ontology':'version-1'}}]
    assert retrieval_query('its properties',turns,scope)=='its properties'
