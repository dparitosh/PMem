import json
import shutil
from unittest.mock import patch
import pytest
from rdflib import Graph, OWL, URIRef
from backend.ontology_service import offline_imports, owl_dl


def source(*iris):
    graph=Graph()
    for iri in iris:graph.add((URIRef('urn:source'),OWL.imports,URIRef(iri)))
    return graph


def test_bundled_imports_resolve_without_network():
    iris=['http://open-services.net/ns/core','http://purl.org/dc/terms/','http://www.w3.org/2004/02/skos/core','http://www.w3.org/ns/shacl']
    with patch('socket.create_connection',side_effect=AssertionError('Network forbidden')):
        closure,missing,resolved,digest=offline_imports.resolve(source(*iris))
    assert not missing and {item['iri'] for item in resolved}==set(iris)
    assert len(closure)>1000 and len(digest)==64
    assert not list(closure.objects(None,OWL.imports))


def test_unknown_import_does_not_start_reasoner():
    with patch.object(owl_dl.subprocess,'run') as run:
        result=owl_dl.inspect_graph(source('https://unknown.invalid/import'),artifact_sha256='x')
    run.assert_not_called()
    assert result['reason']=='unresolved_imports' and not result['consistency_verified']


def test_tampered_vocabulary_fails_closed(tmp_path,monkeypatch):
    shutil.copytree(offline_imports.ROOT,tmp_path,dirs_exist_ok=True)
    manifest=json.loads((tmp_path/'manifest.json').read_text())
    (tmp_path/manifest['documents'][0]['file']).write_text('tampered')
    monkeypatch.setattr(offline_imports,'ROOT',tmp_path)
    with pytest.raises(ValueError,match='digest mismatch'):offline_imports.catalog()
    result=owl_dl.inspect_graph(source('http://www.w3.org/ns/shacl'),artifact_sha256='x')
    assert result['reason']=='offline_import_catalog_invalid'


def test_catalog_path_escape_rejected(tmp_path,monkeypatch):
    (tmp_path/'manifest.json').write_text(json.dumps({'version':1,'documents':[{'file':'../escape.ttl'}]}))
    monkeypatch.setattr(offline_imports,'ROOT',tmp_path)
    with pytest.raises(ValueError,match='Invalid offline import artifact'):offline_imports.catalog()


def test_catalog_revision_invalidates_evidence(tmp_path,monkeypatch):
    before=owl_dl.evidence_key('same-source')
    shutil.copytree(offline_imports.ROOT,tmp_path,dirs_exist_ok=True)
    manifest=tmp_path/'manifest.json';manifest.write_bytes(manifest.read_bytes()+b' ')
    monkeypatch.setattr(offline_imports,'ROOT',tmp_path)
    assert owl_dl.evidence_key('same-source')!=before
