"""Exercise the Windows deployment publication boundary without npm or services."""
from pathlib import Path
import os
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows deployment contract')
@pytest.mark.parametrize('fail', [False, True])
def test_staged_frontend_preserves_open_tab_assets_and_failed_build(tmp_path, fail):
    shell = shutil.which('pwsh') or shutil.which('powershell')
    if not shell:
        pytest.skip('PowerShell unavailable')
    windows = tmp_path / 'infra/windows'
    windows.mkdir(parents=True)
    script = windows / 'build-depo-frontend.ps1'
    shutil.copy2(ROOT / 'infra/windows/build-depo-frontend.ps1', script)
    (windows / 'runtime-config.ps1').write_text('''
function Read-DepoEnvironment { return @{} }
function Resolve-DepoRouting { return @{} }
function Get-DepoNodeRuntime { return @{ Directory=$PSHOME; Node='unused'; Npm='unused'; Version='fixture' } }
function Write-DepoBrowserRouting { param($Root,$EnvFile) Set-Content -LiteralPath (Join-Path $Root 'frontend/dist/depo-runtime-config.js') -Value 'routing' }
''')
    (windows / 'native-install-command.ps1').write_text('''
function Invoke-DepoNativeCommand {
 param($Executable,$NativeArguments)
 $stage=Join-Path (Get-Location) $NativeArguments[-1]
 New-Item -ItemType Directory -Path (Join-Path $stage 'assets') -Force | Out-Null
 Set-Content -LiteralPath (Join-Path $stage 'index.html') -Value 'new-index'
 Set-Content -LiteralPath (Join-Path $stage 'assets/new.js') -Value 'new-asset'
 if ($env:DEPO_BUILD_FAIL -eq '1') { $global:LASTEXITCODE=1 } else { $global:LASTEXITCODE=0 }
}
''')
    for relative, content in [('frontend/dist/index.html','old-index'),
                              ('frontend/dist/assets/old.js','old-asset'),
                              ('frontend/node_modules/.bin/vite.cmd','fixture')]:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    env = {**os.environ, 'DEPO_BUILD_FAIL': '1' if fail else '0'}
    result = subprocess.run([shell, '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                             '-File', str(script)], cwd=tmp_path, env=env,
                            capture_output=True, text=True, timeout=30)
    assert (result.returncode != 0) == fail, result.stdout + result.stderr
    assert (tmp_path / 'frontend/dist/assets/old.js').read_text() == 'old-asset'
    index = (tmp_path / 'frontend/dist/index.html').read_text().strip()
    assert index == ('old-index' if fail else 'new-index')
    assert (tmp_path / 'frontend/dist/assets/new.js').exists() != fail
    assert not list((tmp_path / 'frontend').glob('.depo-build-*'))
