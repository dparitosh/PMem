"""Remote closure contracts: offline mirrors, nested dependencies and safe I/O."""
import socket
import time
from unittest.mock import patch, MagicMock

import pytest
from lxml import etree

from backend.Services import schema_dependencies as schemas


def xsd(body='', namespace='urn:parts'):
    return f'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:p="{namespace}" targetNamespace="{namespace}">{body}</xs:schema>'.encode()


def test_remote_reference_uses_uploaded_mirror_without_network(tmp_path):
    root = xsd('<xs:include schemaLocation="https://schemas.example/types.xsd"/><xs:element name="Part" type="p:PartType"/>')
    files = {'library/types.xsd': xsd('<xs:complexType name="PartType"><xs:attribute name="name" type="xs:string"/></xs:complexType>')}
    with patch.object(schemas, '_download') as fetch:
        resolved, dependencies = schemas.resolve_schema_dependencies('root.xsd', root, files)
    fetch.assert_not_called()
    assert b'library/types.xsd' in resolved
    assert b'https://' in root  # original bytes retained
    assert files == dependencies
    (tmp_path / 'library').mkdir()
    (tmp_path / 'root.xsd').write_bytes(resolved)
    (tmp_path / 'library/types.xsd').write_bytes(files['library/types.xsd'])
    etree.XMLSchema(etree.parse(str(tmp_path / 'root.xsd')))  # QName prefix survives rewrite


def test_recursive_relative_download_is_retained_once_and_compiles(tmp_path):
    root = xsd('<xs:include schemaLocation="https://schemas.example/types.xsd"/><xs:element name="Part" type="p:PartType"/>')
    remote = {
        'https://schemas.example/types.xsd': xsd('<xs:include schemaLocation="common/base.xsd"/>'),
        'https://schemas.example/common/base.xsd': xsd('<xs:complexType name="PartType"><xs:attribute name="name" type="xs:string"/></xs:complexType>'),
    }
    with patch.object(schemas, '_download', side_effect=lambda url, *args: (remote[url], url)) as fetch:
        resolved, files = schemas.resolve_schema_dependencies('root.xsd', root)
    assert fetch.call_count == 2 and len(files) == 2
    (tmp_path / '_remote').mkdir()
    for name, data in {'root.xsd': resolved, **files}.items():
        (tmp_path / name).write_bytes(data)
    etree.XMLSchema(etree.parse(str(tmp_path / 'root.xsd')))
    with patch.object(schemas, '_download') as repeat:
        assert schemas.resolve_schema_dependencies('root.xsd', resolved, files) == (resolved, files)
    repeat.assert_not_called()


def test_cycle_is_finite_and_namespace_mismatch_not_silently_accepted():
    root = xsd('<xs:include schemaLocation="https://schemas.example/a.xsd"/>')
    with patch.object(schemas, '_download', return_value=(root, 'https://schemas.example/a.xsd')) as fetch:
        _, files = schemas.resolve_schema_dependencies('root.xsd', root)
    assert fetch.call_count == 1 and len(files) == 1
    with patch.object(schemas, '_download', return_value=(xsd(namespace='urn:wrong'), 'https://schemas.example/a.xsd')):
        with pytest.raises(ValueError, match='namespace'):
            schemas.resolve_schema_dependencies('root.xsd', root)


@pytest.mark.parametrize('address', ['127.0.0.1', '10.0.2.16', '169.254.169.254', '::1', '0.0.0.0'])
def test_private_dns_addresses_are_rejected_before_connect(address):
    with patch.object(socket, 'getaddrinfo', return_value=[(2, 1, 6, '', (address, 443))]), patch.object(socket, 'create_connection') as connect:
        with pytest.raises(ValueError, match='private'):
            schemas._download('https://schemas.example/part.xsd', 1000, time.monotonic() + 60)
    connect.assert_not_called()


def test_public_address_is_pinned_with_original_tls_hostname():
    connection = MagicMock()
    response = connection.getresponse.return_value
    response.status = 200
    response.read1.side_effect = [xsd(), b'']
    with patch.object(socket, 'getaddrinfo', return_value=[(2, 1, 6, '', ('93.184.216.34', 443))]), patch.object(schemas.http.client, 'HTTPSConnection', return_value=connection) as factory, patch.object(socket, 'create_connection') as dial:
        assert schemas._download('https://schemas.example/part.xsd', 1000, time.monotonic()+60)[0] == xsd()
        connection._create_connection(('schemas.example', 443), 5)
    assert factory.call_args.args == ('schemas.example', 443)
    dial.assert_called_once_with(('93.184.216.34', 443), 5, None)
    assert 'Authorization' not in connection.request.call_args.kwargs['headers']


def test_redirect_is_revalidated_and_oversize_blocked():
    connection = MagicMock()
    response = connection.getresponse.return_value
    response.status = 302
    response.getheader.return_value = 'https://127.0.0.1/private.xsd'
    addresses = [[(2, 1, 6, '', ('93.184.216.34', 443))], [(2, 1, 6, '', ('127.0.0.1', 443))]]
    with patch.object(socket, 'getaddrinfo', side_effect=addresses), patch.object(schemas.http.client, 'HTTPSConnection', return_value=connection) as factory:
        with pytest.raises(ValueError, match='private'):
            schemas._download('https://schemas.example/part.xsd', 1000, time.monotonic()+60)
    assert factory.call_count == 1
    response.status = 200
    response.read1.return_value = b'01234567890'
    with patch.object(schemas, '_public_address', return_value=(schemas.urlsplit('https://schemas.example/x'), 443, '93.184.216.34')), patch.object(schemas.http.client, 'HTTPSConnection', return_value=connection):
        with pytest.raises(ValueError, match='limit'):
            schemas._download('https://schemas.example/x', 10, time.monotonic()+60)


def test_disabled_network_still_allows_local_companion(monkeypatch):
    monkeypatch.setenv('XSD_REMOTE_SCHEMA_ENABLED', 'false')
    root = xsd('<xs:include schemaLocation="https://schemas.example/types.xsd"/>')
    with pytest.raises(ValueError, match='disabled'):
        schemas.resolve_schema_dependencies('root.xsd', root)
    assert schemas.resolve_schema_dependencies('root.xsd', root, {'types.xsd': xsd()})[1]


def test_remote_html_dtd_and_timeout_report_recoverable_dependency_error():
    root = xsd('<xs:include schemaLocation="https://schemas.example/types.xsd"/>')
    for data in (b'<html/>', b'<!DOCTYPE schema [<!ENTITY a "b">]><schema/>'):
        with patch.object(schemas, '_download', return_value=(data, 'https://schemas.example/types.xsd')):
            with pytest.raises(ValueError, match='safe XML Schema'):
                schemas.resolve_schema_dependencies('root.xsd', root)
    with patch.object(schemas, '_download', side_effect=TimeoutError('private server detail')):
        with pytest.raises(ValueError, match='supply a local companion') as error:
            schemas.resolve_schema_dependencies('root.xsd', root)
        assert 'private server detail' not in str(error.value)


def test_engineering_conversion_retains_resolved_closure_and_original(monkeypatch):
    from backend.ingestion_service import schema_conversion
    from backend.Services import owl_generation_service
    from rdflib import Graph, URIRef
    from rdflib.namespace import OWL, RDF
    artifacts = []
    class Store:
        def ingest_bytes(self, content, **metadata):
            row = {'artifact_id': f'artifact-{len(artifacts)}', 'content': content, **metadata}
            artifacts.append(row)
            return row
    monkeypatch.setattr(schema_conversion, 'ArtifactStore', Store)
    monkeypatch.setattr(owl_generation_service, '_inspect_with_owlready', lambda *args: {})
    root = xsd('<xs:include schemaLocation="https://schemas.example/types.xsd"/><xs:element name="Part" type="p:PartType"/>')
    remote = xsd('<xs:complexType name="PartType"><xs:attribute name="mass" type="xs:decimal"/></xs:complexType>')
    with patch.object(schemas, '_download', return_value=(remote, 'https://schemas.example/types.xsd')) as fetch:
        result = schema_conversion.EngineeringSchemaConverter().convert(filename='product.xsd', content=root)
    assert fetch.call_count == 1
    graph = Graph().parse(data=result['ontology']['turtle'], format='turtle')
    assert any('PartType' in str(subject) for subject in graph.subjects(RDF.type, OWL.Class))
    assert not result['structural_model']['ddl_blockers']
    assert any(key.startswith('dependency:') for key in result['artifacts'])
    original = next(row for row in artifacts if row['kind'] == 'engineering-schema-original')
    source = next(row for row in artifacts if row['artifact_id'] == result['artifacts']['source'])
    assert original['content'] == root
    assert source['provenance']['original_source_artifact_id'] == original['artifact_id']
    assert b'https://schemas.example' not in source['content']


def test_allowlist_and_ambiguous_companions_never_fall_back_to_network(monkeypatch):
    monkeypatch.setenv('XSD_REMOTE_SCHEMA_HOSTS', 'approved.example')
    with patch.object(socket, 'getaddrinfo') as dns:
        with pytest.raises(ValueError, match='XSD_REMOTE_SCHEMA_HOSTS'):
            schemas._public_address('https://other.example/a.xsd')
    dns.assert_not_called()
    root = xsd('<xs:include schemaLocation="https://approved.example/a.xsd"/>')
    with patch.object(schemas, '_download') as fetch:
        with pytest.raises(ValueError, match='ambiguous'):
            schemas.resolve_schema_dependencies('root.xsd', root, {'one/a.xsd': xsd(), 'two/a.xsd': xsd()})
        with pytest.raises(ValueError, match='namespace'):
            schemas.resolve_schema_dependencies('root.xsd', root, {'a.xsd': xsd(namespace='urn:wrong')})
    fetch.assert_not_called()
