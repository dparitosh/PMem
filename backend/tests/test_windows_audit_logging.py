import json
import shutil
import subprocess
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('absolute', [False, True])
def test_selected_environment_secrets_are_redacted_before_import(tmp_path, absolute):
    shell = shutil.which('powershell.exe')
    if not shell:
        pytest.skip('Windows PowerShell required')
    selected = tmp_path / 'selected.env'
    selected.write_text('ADMIN_API_KEY=selected-test-secret-987654\n')
    script = tmp_path / 'run.ps1'
    env_argument = str(selected) if absolute else 'selected.env'
    helper = ROOT / 'infra/windows/native-install-command.ps1'
    script.write_text(f". '{helper}'\nInvoke-DepoLoggedAction -Root '{tmp_path}' -Name selected -AuditEnvFile '{env_argument}' -Action {{throw 'failure selected-test-secret-987654'}}")
    result = subprocess.run([shell, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script)], capture_output=True, text=True)
    assert result.returncode != 0
    output = result.stdout + result.stderr
    for log in (tmp_path / 'logs/installation/runs').glob('*'):
        output += log.read_text(encoding='utf-8')
    assert 'selected-test-secret-987654' not in output
    assert '[REDACTED]' in output

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


@pytest.mark.parametrize("exit_code", [0, 23])
def test_native_python_info_stderr_preserves_json_and_checks_exit(tmp_path, exit_code):
    import sys
    shell = shutil.which("powershell.exe")
    if not shell:
        pytest.skip("Windows PowerShell required")
    helper = ROOT / "infra/windows/native-install-command.ps1"
    script = tmp_path / "native.ps1"
    python_source = "import sys, json\nprint('INFO: parser imports OK', file=sys.stderr)\nprint(json.dumps({'mode':'existing'}))\nsys.exit(" + str(exit_code) + ")\n"
    ps = "$ErrorActionPreference='Stop'\n. '" + str(helper) + "'\nInvoke-DepoLoggedAction -Root '" + str(tmp_path) + "' -Name 'native-test' -Action {\n$info = @'\n" + python_source + "'@ | Invoke-DepoNativeCommand -Executable '" + sys.executable + "' -NativeArguments @('-')\nif (($info | ConvertFrom-Json).mode -ne 'existing') {throw 'stdout corrupted'}\n}\n"
    script.write_text(ps)
    result = subprocess.run([shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)], capture_output=True, text=True)
    assert (result.returncode == 0) == (exit_code == 0), result.stdout + result.stderr
    logs = list((tmp_path / "logs/installation/runs").glob("*.jsonl"))
    events = [json.loads(line) for line in logs[0].read_text(encoding="utf-8").splitlines()]
    assert any("INFO: parser imports OK" in event["message"] for event in events)
    assert events[-1]["level"] == ("succeeded" if exit_code == 0 else "failed")


@pytest.mark.parametrize("exit_code", [0, 17])
def test_actual_npm_retry_block_retains_warning_and_obeys_exit(tmp_path, exit_code):
    shell = shutil.which("powershell.exe")
    if not shell:
        pytest.skip("Windows PowerShell required")
    stub = tmp_path / 'npm.cmd'
    stub.write_text('@echo off\necho npm warn deprecated fixture-warning 1>&2\nexit /b ' + str(exit_code) + '\n')
    source = (ROOT / 'infra/windows/install-depo.ps1').read_text()
    begin = source.index('    for ($attempt = 1;')
    end = source.index('    } -Probe {', begin)
    block = source[begin:end]
    script = tmp_path / 'npm-test.ps1'
    helper = ROOT / 'infra/windows/native-install-command.ps1'
    script.write_text("$ErrorActionPreference='Stop'\n. '" + str(helper) + "'\nfunction Start-Sleep {}\n$installLogDir='" + str(tmp_path) + "'\n$nodeRuntime=@{Npm='" + str(stub) + "'}\nInvoke-DepoLoggedAction -Root '" + str(tmp_path) + "' -Name npm -Action {\n" + block + "\n}\n")
    result = subprocess.run([shell, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script)], capture_output=True, text=True)
    assert (result.returncode == 0) == (exit_code == 0), result.stdout + result.stderr
    attempts = list(tmp_path.glob('npm-ci-*.log'))
    assert len(attempts) == (1 if exit_code == 0 else 3)
    assert all('fixture-warning' in log.read_text() for log in attempts)


@pytest.mark.parametrize("exit_code", [0, 17])
def test_npm_build_stderr_is_not_a_powershell_failure(tmp_path, exit_code):
    shell = shutil.which('powershell.exe')
    if not shell:
        pytest.skip('Windows PowerShell required')
    stub = tmp_path / 'npm.cmd'
    stub.write_text('@echo off\necho npm warn deprecated build-fixture 1>&2\nexit /b ' + str(exit_code) + '\n')
    script = tmp_path / 'build.ps1'
    helper = ROOT / 'infra/windows/native-install-command.ps1'
    script.write_text("$ErrorActionPreference='Stop'\n. '" + str(helper) + "'\nInvoke-DepoLoggedAction -Root '" + str(tmp_path) + "' -Name build -Action {Invoke-DepoNativeCommand -Executable '" + str(stub) + "' -NativeArguments @('run','build')}\n")
    result = subprocess.run([shell, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script)], capture_output=True, text=True)
    assert (result.returncode == 0) == (exit_code == 0), result.stdout + result.stderr
    assert 'build-fixture' in result.stdout
