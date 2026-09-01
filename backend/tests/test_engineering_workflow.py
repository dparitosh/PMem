import pytest

from backend.ingestion_service.engineering_workflow import EngineeringWorkflow


class StubConverter:
    def convert(self, *, filename, content):
        return {
            "format": "EXPRESS", "source_kind": "schema", "statistics": {}, "next_action": "register",
            "ontology": {"name": "Demo", "prefix": "exp", "base_uri": "https://example.test/exp#", "turtle": "@prefix ex: <https://example.test/> ."},
        }


@pytest.mark.asyncio
async def test_engineering_workflow_can_return_conversion_without_cross_service_write():
    result = await EngineeringWorkflow(StubConverter()).run(filename="demo.exp", content=b"SCHEMA demo; END_SCHEMA;", register=False)
    assert result["status"] == "converted"
    assert result["conversion"]["format"] == "EXPRESS"
