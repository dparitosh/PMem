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


if __name__ == "__main__":
    unittest.main()
