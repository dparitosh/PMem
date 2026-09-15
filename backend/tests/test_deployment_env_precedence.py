from backend.core import db_config


def test_legacy_dotenv_cannot_override_deployment_environment(monkeypatch):
    calls = []
    monkeypatch.setattr(db_config.Path, "exists", lambda self: True)
    monkeypatch.setattr(db_config, "load_dotenv", lambda path, **kwargs: calls.append(kwargs))
    db_config._load_environment()
    assert calls == [{"override": False}]
