import pytest
from backend.data_pipeline_service.handlers import HandlerRegistry, JobHandler, registry


def test_duplicate_and_unknown_handlers_fail_closed():
    handlers = HandlerRegistry()
    handler = JobHandler("in-v1", "out-v1", lambda *args: {})
    handlers.register("custom", handler)
    with pytest.raises(ValueError):
        handlers.register("custom", handler)
    with pytest.raises(ValueError):
        handlers.get("unknown")


def test_validation_strategy_cannot_silently_become_normalization():
    class Runner:
        def normalize_ceim_batch(self, payload, *, correlation_id, validate):
            return {"validate": validate, "correlation": correlation_id}
    result = registry.get("validate-semantic-batch").execute(Runner(), {}, correlation_id="test")
    assert result == {"validate": True, "correlation": "test"}


def test_unstructured_ceim_handler_is_explicit_and_governed():
    class Runner:
        def normalize_unstructured_ceim(self, payload, *, correlation_id):
            return {"payload": payload, "correlation": correlation_id}
    result = registry.get("normalize-unstructured-ceim").execute(Runner(), {"proposal_artifact_id": "sha256:test"}, correlation_id="test")
    assert result["payload"]["proposal_artifact_id"] == "sha256:test"


def test_schema_analytics_handler_is_a_distinct_governed_strategy():
    class Runner:
        def build_schema_analytics_product(self, payload, *, correlation_id):
            return {"payload": payload, "correlation": correlation_id}
    result = registry.get("schema-analytics-product").execute(Runner(), {"artifact_id": "sha256:test"}, correlation_id="test")
    assert result["payload"]["artifact_id"] == "sha256:test"
