"""Dependency-free tests of published credential names, never secrets."""
import unittest
from types import SimpleNamespace
from backend.depo_platform.openapi_contract import credential_profiles, describe_security


def graph_read_identity():
    pass


def require_admin_api_key():
    pass


def approval_identity(*args, **kwargs):
    pass


def service_write_identity(*args, **kwargs):
    pass


def write_endpoint():
    service_write_identity(None, token_env="GRAPH_PUBLICATION_TOKEN", default_actor="publisher")


def approval_endpoint():
    approval_identity(None, {}, token_env="DATA_PRODUCT_APPROVAL_TOKEN")


def _ingestion_identity():
    pass


def _qif_identity():
    service_write_identity(None, token_env="ONTOLOGY_APPROVAL_TOKEN", default_actor="qif")


def public_endpoint():
    pass


class CredentialProfiles(unittest.TestCase):
    def test_nested_router_authorization_keeps_the_effective_prefix(self):
        from fastapi import FastAPI, APIRouter
        child = APIRouter()
        child.post('/publish')(approval_endpoint)
        parent = APIRouter()
        parent.include_router(child, prefix='/child')
        app = FastAPI()
        app.include_router(parent, prefix='/api/v1')
        document = describe_security(app.openapi(), app.routes)
        operation = document['paths']['/api/v1/child/publish']['post']
        self.assertEqual(operation['x-depo-authorization']['credential_profiles'], ['DATA_PRODUCT_APPROVAL_TOKEN'])
        self.assertIn({}, operation['security'])

    def test_modeling_read_guard_requires_graph_read_access(self):
        def _modeling_identity(): pass
        route = SimpleNamespace(path_format='/ontologies/health', endpoint=public_endpoint, methods={'GET'},
            dependant=SimpleNamespace(dependencies=[SimpleNamespace(call=_modeling_identity, dependencies=[])]))
        operation = describe_security({'paths': {'/ontologies/health': {'get': {}}}}, [route])['paths']['/ontologies/health']['get']
        self.assertEqual(operation['x-depo-authorization']['credential_profiles'], ['GRAPH_READ_TOKEN'])
        self.assertNotIn({}, operation['security'])

    def test_exact_header_and_approval_names(self):
        self.assertEqual(credential_profiles(write_endpoint, [], method="POST", path="/publish"), ["GRAPH_PUBLICATION_TOKEN"])
        self.assertEqual(credential_profiles(approval_endpoint, [], method="POST", path="/publish"), ["DATA_PRODUCT_APPROVAL_TOKEN"])
        self.assertEqual(credential_profiles(public_endpoint, [graph_read_identity], method="GET", path="/read"), ["GRAPH_READ_TOKEN"])
        self.assertEqual(credential_profiles(public_endpoint, [require_admin_api_key], method="POST", path="/admin"), ["ADMIN_API_KEY"])

    def test_method_and_path_sensitive_dependencies(self):
        for path, expected in [("/api/v1/governed-import", "DATA_JOB_EXECUTION_TOKEN"), ("/api/v1/sysml-v2/import-commit", "DATA_JOB_EXECUTION_TOKEN"), ("/api/v1/ontology/upload", "INGESTION_WRITE_TOKEN")]:
            self.assertEqual(credential_profiles(public_endpoint, [_ingestion_identity], method="POST", path=path), [expected])
        self.assertEqual(credential_profiles(public_endpoint, [_qif_identity], method="GET", path="/qif"), [])
        self.assertEqual(credential_profiles(public_endpoint, [_qif_identity], method="POST", path="/qif"), ["ONTOLOGY_APPROVAL_TOKEN"])

    def test_schema_extension_contains_name_only(self):
        route = SimpleNamespace(path_format="/publish", endpoint=approval_endpoint, methods={"POST"}, dependant=SimpleNamespace(dependencies=[]))
        doc = describe_security({"paths": {"/publish": {"post": {}}}}, [route])
        metadata = doc["paths"]["/publish"]["post"]["x-depo-authorization"]
        self.assertEqual(metadata["credential_profiles"], ["DATA_PRODUCT_APPROVAL_TOKEN"])
        self.assertEqual(metadata["resolution"], "explicit")
        self.assertEqual(metadata["approval_fields"], ["approved_by", "approval_token"])

    def test_service_header_check_does_not_advertise_body_approval(self):
        route = SimpleNamespace(path_format='/write', endpoint=write_endpoint, methods={'POST'}, dependant=SimpleNamespace(dependencies=[]))
        document = describe_security({'paths': {'/write': {'post': {}}}}, [route])
        operation = document['paths']['/write']['post']
        self.assertEqual(operation['x-depo-authorization']['approval_fields'], [])
        self.assertNotIn({}, operation['security'])

    def test_metadata_migration_and_normal_routes_advertise_distinct_credentials(self):
        def _metadata_registry_identity(): pass
        for method,path,expected in [('POST','/metadata-registry/migrations/postgres','ADMIN_API_KEY'),
                                     ('POST','/metadata-registry/assets','ONTOLOGY_APPROVAL_TOKEN'),
                                     ('GET','/metadata-registry/assets','GRAPH_READ_TOKEN')]:
            self.assertEqual(credential_profiles(public_endpoint,[_metadata_registry_identity],method=method,path=path),[expected])


if __name__ == "__main__":
    unittest.main()
