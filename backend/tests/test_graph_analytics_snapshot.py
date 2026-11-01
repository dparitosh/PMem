"""Graph snapshot version fencing and deterministic registration."""
from unittest.mock import patch
import httpx,pytest
from backend.data_pipeline_service.graph_snapshot import register_graph_snapshot


def reply(value):return httpx.Response(200,json=value,request=httpx.Request('GET','http://graph'))


def test_snapshot_rejects_publication_change_before_registry_write():
    snapshot={'ontology_id':'source','namespace':'','publication':{'publication_id':'new'},'content':'<urn:a> <urn:p> <urn:b> .','triples':1,'scope':'published'}
    with patch('backend.data_pipeline_service.graph_snapshot.service_url',return_value='http://local'),patch('backend.data_pipeline_service.graph_snapshot.service_bearer_headers',return_value={}),patch('backend.data_pipeline_service.graph_snapshot.peer_response',return_value=reply(snapshot)) as peer:
        with pytest.raises(ValueError,match='changed'):register_graph_snapshot({'ontology_id':'source','graph_publication_id':'old'},'test')
        assert peer.call_count==1


def test_snapshot_retry_registers_identical_rdf_with_publication_provenance():
    snapshot={'ontology_id':'source','namespace':'','publication':{'publication_id':'published'},'content':'<urn:a> <urn:p> <urn:b> .','triples':1,'scope':'published'}
    sent=[]
    def peer(method,url,**kwargs):
        if method=='GET':return reply(snapshot)
        sent.append(kwargs['files']['file'][1]);return reply({'artifact_id':'sha256:source','source_id':'metadata:registered'})
    with patch('backend.data_pipeline_service.graph_snapshot.service_url',return_value='http://local'),patch('backend.data_pipeline_service.graph_snapshot.service_bearer_headers',return_value={}),patch('backend.data_pipeline_service.graph_snapshot.peer_response',side_effect=peer):
        for _ in range(2):
            result=register_graph_snapshot({'ontology_id':'source','graph_publication_id':'published'},'test')
            assert result['source_id']=='metadata:registered'
    assert sent[0]==sent[1]
    assert b'http://purl.org/dc/terms/identifier' in sent[0]


def test_read_only_analysis_cannot_execute_new_write_operations():
    from backend.data_pipeline_service.semantic_analysis import analyse
    for operation in ('business-mart','graph-snapshot'):
        with pytest.raises(ValueError):analyse({'algorithm':operation,'dataset_id':'a'*64,'class_iri':'urn:Part'})
