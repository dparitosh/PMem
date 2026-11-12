import importlib.util
from pathlib import Path


def test_frontend_endpoint_defaults_match_published_service_contracts():
    root = Path(__file__).resolve().parents[2]
    script = root / "scripts" / "frontend_api_contract.py"
    spec = importlib.util.spec_from_file_location("frontend_api_contract", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    report = module.classify_contract()

    assert report["status"] == "pass", report["unclassified"]
    assert report["configured_backend_endpoint_count"] > 100
    assert report["matched_backend_endpoint_count"] == report["configured_backend_endpoint_count"]
    assert report["external_agentic_endpoint_count"] == 0
    assert report["service_contract_count"] == 10


def test_static_classifier_does_not_confuse_service_aliases_and_runtime_paths():
    import runpy
    module=runpy.run_path(str(Path(__file__).resolve().parents[2]/'scripts/frontend_api_contract.py'))
    config=r"""const QIF_ENDPOINTS = {
 catalog: setting('QIF_CATALOG') || '/api/v1/qif/catalog'
};
export const API = {
 qif: QIF_ENDPOINTS
};
const SERVICE_PATHS = [
 ['qif', /^\/api\/v1\/qif/]
];"""
    calls="""apiClient.get(buildUrl(API.qif.catalog));
apiClient.get(buildUrl(`${API.qif.catalog.replace(/catalog$/, '')}/${id}/status`));
apiClient.get(buildSemanticServiceUrl('qif', '/api/v1/qif/tasks'));
"""
    operations,unresolved=module['frontend_operations'](config,[('fixture.js',calls)])
    assert len(operations)==2 and all(op['service']=='schema-sets' for op in operations)
    assert len(unresolved)==1 and '.replace' in unresolved[0]['expression']
