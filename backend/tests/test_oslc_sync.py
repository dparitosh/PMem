import pytest

from backend.oslc_service.client import OSLCClient
from backend.oslc_service.sync import OSLCSyncStore, OSLCSynchronizer


class FakeOSLCClient:
    def query(self, resource_type, parameters):
        return {"value": [{"id": "R-1", "type": resource_type, "params": parameters}]}


def test_oslc_pull_sync_stages_an_auditable_snapshot(tmp_path):
    store = OSLCSyncStore()
    store.root = tmp_path
    synchronizer = OSLCSynchronizer(FakeOSLCClient(), store)

    snapshot = synchronizer.pull("Requirement", {"oslc.where": "status=approved"})

    assert snapshot["status"] == "staged"
    assert snapshot["resource_count"] == 1
    assert store.get(snapshot["sync_id"])["resources"][0]["id"] == "R-1"


def test_oslc_sync_store_rejects_non_uuid_snapshot_paths(tmp_path):
    store = OSLCSyncStore()
    store.root = tmp_path
    assert store.get("../../sensitive") is None


def test_oslc_client_rejects_unsafe_resource_type_before_network_access():
    with pytest.raises(ValueError, match="resource_type"):
        OSLCClient().query("../catalog", {})
