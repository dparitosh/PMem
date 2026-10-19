import json
import shutil
import subprocess
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]

@pytest.mark.parametrize("mode", ["success", "throw", "native", "write_error", "continue_error"])
def test_entrypoint_retains_errors_and_redacts_credentials(tmp_path, mode):
    shell = shutil.which("powershell.exe")
    if not shell:
        pytest.skip("Windows PowerShell required")
    (tmp_path / ".env.local").write_text("ADMIN_API_KEY=test-secret-marker-987654\n")
    body = {
        "success": "Write-Host 'hello test-secret-marker-987654'; Write-Warning 'warning retained'",
        "throw": "throw 'failure test-secret-marker-987654'",
        "native": "& cmd.exe /d /c 'echo native-error 1>&2 & exit /b 19'",
        "continue_error": "Write-Error 'continued failure' -ErrorAction Continue",
        "write_error": "Write-Error 'nonterminating failure' -ErrorAction Stop",
    }[mode]
    script = tmp_path / "run.ps1"
    helper = ROOT / "infra/windows/native-install-command.ps1"
    script.write_text(f"$ErrorActionPreference='Stop'\n. '{helper}'\nInvoke-DepoLoggedAction -Root '{tmp_path}' -Name 'test' -Action {{ {body} }}\n")
    result = subprocess.run([shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)], capture_output=True, text=True)
    logs = list((tmp_path / "logs/installation/runs").glob("*.jsonl"))
    assert len(logs) == 1
    events = [json.loads(line) for line in logs[0].read_text(encoding="utf-8").splitlines()]
    assert events[0]["level"] == "started"
    assert events[-1]["level"] == ("succeeded" if mode == "success" else "failed")
    assert (result.returncode == 0) == (mode == "success")
    retained = logs[0].read_text(encoding="utf-8")
    assert "test-secret-marker-987654" not in result.stdout + result.stderr
    assert "test-secret-marker-987654" not in retained
    if mode in ("throw", "success"):
        assert "[REDACTED]" in retained
    if mode == "native":
        assert "native-error" in retained
