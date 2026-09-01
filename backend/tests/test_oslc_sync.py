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
