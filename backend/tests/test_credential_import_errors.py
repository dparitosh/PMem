import io
import json
from unittest.mock import patch

from backend.depo_platform import credential_import as ci


def test_unexpected_failure_reports_its_type_and_no_key_values(capsys, monkeypatch):
    monkeypatch.setattr("sys.argv", ["credential_import"])
    monkeypatch.setattr(ci, "uses_postgres", lambda: True)
    monkeypatch.setattr(ci, "apply_values", lambda values, replace=False: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(b'\xef\xbb\xbf{"ADMIN_API_KEY": "secret-value"}')))
    assert ci.main() == 1
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["status"] == "failed"
    assert "RuntimeError" in out["action"]
    assert "secret-value" not in json.dumps(out)
