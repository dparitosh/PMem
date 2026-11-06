from fastapi.testclient import TestClient
from mbse_plugin.app import app
from mbse_plugin.cameo_mdk.config import CameoConfig, inspect_local


def test_cameo_offline_contract(monkeypatch, tmp_path):
    monkeypatch.setenv('MBSE_PLUGIN_TOKEN', 'test')
    client = TestClient(app)
    headers = {'Authorization': 'Bearer test'}
    assert client.get('/cameo-mdk/template').status_code == 401
    data = client.get('/cameo-mdk/template', headers=headers).json()
    assert client.post('/cameo-mdk/validate', headers=headers, json=data).json()['compatibility'] == 'unverified'
    data['native_operations_enabled'] = True
    assert client.post('/cameo-mdk/validate', headers=headers, json=data).status_code == 422
    result = inspect_local(CameoConfig(cameo_home=str(tmp_path)))
    assert result['checks']['cameo_directory_exists']
    assert not result['checks']['mdk_descriptor_exists']
