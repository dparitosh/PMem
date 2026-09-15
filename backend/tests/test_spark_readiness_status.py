from backend.data_pipeline_service.runner import SparkJobRunner


def test_enabled_missing_runtime_is_not_healthy(monkeypatch, tmp_path):
    monkeypatch.setenv("DEPO_SPARK_ENABLED", "true")
    monkeypatch.setenv("DEPO_SPARK_HOME", str(tmp_path / "missing-spark"))
    monkeypatch.setenv("DEPO_JAVA_HOME", str(tmp_path / "missing-java"))
    health = SparkJobRunner().health()
    assert health["status"] == "unavailable"
    assert health["runtime_files_present"] is False
    assert health["execution_verified"] is False


def test_disabled_runtime_remains_disabled(monkeypatch):
    monkeypatch.setenv("DEPO_SPARK_ENABLED", "false")
    assert SparkJobRunner().health()["status"] == "disabled"
