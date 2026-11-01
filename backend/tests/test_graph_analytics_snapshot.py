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

def test_export_uses_transaction_strings_and_preserves_literal_datatypes():
    from contextlib import nullcontext
    from backend.graph_service import analytics_snapshot as export
    from rdflib import Graph,URIRef,Literal
    class Rows:
        def __init__(self,rows):self.rows=rows
        def data(self):return self.rows
    class Tx:
        def run(self,query,**kwargs):
            assert isinstance(query,str),'Explicit transaction.run requires a query string'
            if 'OntologyPublication' in query:return Rows([{'publication_id':'published','artifact_sha256':None}])
            if 'n.rdf_types' in query:return Rows([{'iri':'urn:part','kind':'individual','types':['urn:Part'],'properties':'{"urn:mass":[{"value":"1.50","datatype":"http://www.w3.org/2001/XMLSchema#decimal","language":null}]}'}])
            return Rows([])
        def commit(self):pass
        def rollback(self):pass
    class Session:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def begin_transaction(self,**kwargs):assert kwargs['timeout']==25;return Tx()
    class Driver(Session):
        def session(self,**kwargs):return Session()
    with patch.object(export,'projection_access',return_value=nullcontext()),patch.object(export.publisher,'_driver',return_value=Driver()):
        result=export.projection_snapshot('source')
        graph=Graph().parse(data=result['content'],format='nt')
        assert len(graph)==2
        assert (URIRef('urn:part'),URIRef('urn:mass'),Literal('1.50',datatype=URIRef('http://www.w3.org/2001/XMLSchema#decimal'))) in graph
