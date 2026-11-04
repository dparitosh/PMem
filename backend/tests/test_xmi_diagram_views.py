from pathlib import Path
import pytest
from backend.ontology_service.xmi_diagrams import read_diagrams


def test_named_view_keeps_source_members_and_not_other_elements(tmp_path):
    path=tmp_path/'model.xmi'
    path.write_text("""<xmi:XMI xmlns:xmi="http://www.omg.org/XMI" xmlns:uml="http://www.omg.org/spec/UML/20131001"><uml:Model xmi:id="m"><packagedElement xmi:type="uml:Class" xmi:id="a" name="Motor"/><packagedElement xmi:type="uml:Class" xmi:id="b" name="Bearing"/><packagedElement xmi:type="uml:Class" xmi:id="outside" name="Other"/><ownedDiagram xmi:id="view" name="Drive BDD"><DiagramRepresentationObject type="SysML Block Definition Diagram"><diagramContents><binaryObject streamContentID="not-in-this-file"/><usedObjects href="#a"/><usedObjects href="#b"/><usedObjects href="#missing"/></diagramContents></DiagramRepresentationObject></ownedDiagram></uml:Model></xmi:XMI>""")
    data=read_diagrams(path)
    view=data['representations'][0]
    assert view['nodeIds']==['a','b']
    assert view['unresolvedIds']==['missing']
    assert view['external_layout'] is True
    assert view['layout']=='generated'
    assert next(node for node in data['nodes'] if node['id']=='a')['label']=='Motor'


def test_no_named_diagrams_is_explicit(tmp_path):
    path=tmp_path/'model.xmi';path.write_text('<xmi:XMI xmlns:xmi="http://www.omg.org/XMI"><Model xmi:id="m"/></xmi:XMI>')
    with pytest.raises(ValueError,match='no named diagram'):
        read_diagrams(path)


def test_dtd_rejected(tmp_path):
    path=tmp_path/'model.xmi';path.write_text('<!DOCTYPE xmi:XMI [<!ENTITY bad SYSTEM "file:///secret">]><xmi:XMI xmlns:xmi="http://www.omg.org/XMI"/>')
    with pytest.raises(ValueError,match='DTD'):
        read_diagrams(path)


def test_route_requires_read_authorization_and_returns_manifest(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.ontology_service.modeling_router import router
    from backend.ontology_service import xmi_diagrams
    monkeypatch.setenv('AUTH_MODE','token');monkeypatch.setenv('GRAPH_READ_TOKEN','read-only-test')
    app=FastAPI();app.include_router(router,prefix='/api/v1')
    monkeypatch.setattr(xmi_diagrams,'retained_diagrams',lambda identity:{'ontology_id':identity,'representations':[]})
    client=TestClient(app)
    assert client.get('/api/v1/modeling/xmi-diagrams/model-v1').status_code==403
    result=client.get('/api/v1/modeling/xmi-diagrams/model-v1',headers={'Authorization':'Bearer read-only-test'})
    assert result.status_code==200
    assert result.json()['ontology_id']=='model-v1'


def test_malformed_xml_has_validation_error(tmp_path):
    path = tmp_path / 'broken.xmi'
    path.write_text('<broken>')
    with pytest.raises(ValueError, match='not well-formed'):
        read_diagrams(path)


def test_context_resolves_exact_scoped_identity_and_neighbors(monkeypatch):
    from backend.ontology_service import xmi_diagrams
    from backend.core import graph
    monkeypatch.setattr(xmi_diagrams, 'retained_diagrams', lambda identity: {'nodes':[{'id':'original'}]})
    calls=[]
    def query(text, params, timeout):
        calls.append((text, params))
        if 'LIMIT 2' in text:
            return [{'id':'graph-id','properties':{'name':'Drive'}}]
        return [{'id':'cad','properties':{'cad_url':'https://cad.example/42'},'labels':['CAD'],
                 'relationship_id':'rel','relationship':'HAS_DESIGN','source':'graph-id','target':'cad'}]
    monkeypatch.setattr(graph, 'query_with_timeout', query)
    result = xmi_diagrams.model_context('version-42','original')
    assert result['node_id']=='graph-id'
    assert result['nodes'][0]['properties']['cad_url']=='https://cad.example/42'
    assert calls[0][1]['ontology_id']=='version-42'
    assert calls[0][1]['suffix']=='/original'
    with pytest.raises(LookupError):
        xmi_diagrams.model_context('version-42','not-in-source')


def test_ambiguous_context_cannot_supply_agent_identity(monkeypatch):
    from backend.ontology_service import xmi_diagrams
    from backend.core import graph
    monkeypatch.setattr(xmi_diagrams, 'retained_diagrams', lambda identity: {'nodes':[{'id':'original'}]})
    monkeypatch.setattr(graph, 'query_with_timeout', lambda *args, **kwargs:[{'id':'one'},{'id':'two'}])
    result=xmi_diagrams.model_context('version','original')
    assert result['status']=='ambiguous'
    assert 'node_id' not in result


def test_context_failure_is_sanitized_and_read_authorized(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.ontology_service.modeling_router import router
    from backend.ontology_service import xmi_diagrams
    monkeypatch.setenv('AUTH_MODE','token');monkeypatch.setenv('GRAPH_READ_TOKEN','read-only-test')
    app=FastAPI();app.include_router(router,prefix='/api/v1')
    def unavailable(*args):
        raise xmi_diagrams.ModelContextUnavailable('Engineering associations are temporarily unavailable')
    monkeypatch.setattr(xmi_diagrams,'model_context',unavailable)
    client=TestClient(app)
    url='/api/v1/modeling/xmi-context/version?source_id=original'
    assert client.get(url).status_code==403
    response=client.get(url,headers={'Authorization':'Bearer read-only-test'})
    assert response.status_code==503
    assert 'temporarily unavailable' in response.json()['detail']


def test_context_truncation_is_explicit(monkeypatch):
    from backend.ontology_service import xmi_diagrams
    monkeypatch.setattr(xmi_diagrams, 'retained_diagrams', lambda identity:{'nodes':[{'id':'original'}]})
    def query(text, params):
        if 'LIMIT 2' in text:
            return [{'id':'graph-id','properties':{}}]
        return [{'id':str(i),'properties':{},'labels':[],'relationship_id':str(i),'relationship':'TRACE','source':'graph-id','target':str(i)} for i in range(101)]
    monkeypatch.setattr(xmi_diagrams,'_context_query',query)
    result=xmi_diagrams.model_context('version','original')
    assert result['truncated'] is True
    assert len(result['links'])==100
