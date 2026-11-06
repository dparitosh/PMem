"""Exercise untrusted dictionary handling with the supported patched runtime."""
import json

from langchain_core.load import dumps, loads


def test_serialization_preserves_secret_shaped_user_data(monkeypatch):
    monkeypatch.setenv('PMEM_SERIALIZATION_FIXTURE', 'fixture-secret-not-a-credential')
    payload = {'metadata': {'lc': 1, 'type': 'secret', 'id': ['PMEM_SERIALIZATION_FIXTURE']}}
    encoded = dumps(payload)
    assert loads(encoded, secrets_from_env=False, allowed_objects=[]) == payload
    assert 'fixture-secret-not-a-credential' not in encoded


def test_deserialization_respects_explicit_secret_denial(monkeypatch):
    monkeypatch.setenv('PMEM_SERIALIZATION_FIXTURE', 'fixture-secret-not-a-credential')
    encoded = json.dumps({'lc': 1, 'type': 'secret', 'id': ['PMEM_SERIALIZATION_FIXTURE']})
    # No secret map was explicitly granted to the deserializer.
    try:
        result = loads(encoded, secrets_from_env=False, allowed_objects=[])
    except (ValueError, KeyError):
        return
    assert result != 'fixture-secret-not-a-credential'
