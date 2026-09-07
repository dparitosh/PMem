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
