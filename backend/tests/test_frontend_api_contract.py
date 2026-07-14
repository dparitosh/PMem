import importlib.util
from pathlib import Path


def test_frontend_endpoint_defaults_match_openapi_or_external_service():
    root = Path(__file__).resolve().parents[2]
    script = root / "scripts" / "frontend_api_contract.py"
    spec = importlib.util.spec_from_file_location("frontend_api_contract", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    report = module.classify_contract()

    assert report["status"] == "pass", report["unclassified"]
    assert report["matched_backend_endpoint_count"] == report["configured_backend_endpoint_count"]
    assert report["external_agentic_endpoint_count"] == 6
