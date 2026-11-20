"""Process visibility failures must be detected before a batch stop starts."""
from pathlib import Path
import shutil
import subprocess
import pytest

ROOT=Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('hidden,valid', [(True,False),(False,True)])
def test_all_tracked_service_identities_are_checked_before_shutdown(tmp_path,hidden,valid):
    shell=shutil.which('powershell.exe')
    if not shell:pytest.skip('Windows PowerShell required')
    (tmp_path/'logs/windows-services').mkdir(parents=True)
    (tmp_path/'infra/deployment').mkdir(parents=True)
    (tmp_path/'infra/deployment/services.json').write_text('{"workers":[],"services":[{"id":"first","module":"first.service"},{"id":"second","module":"second.service"}]}')
    (tmp_path/'logs/windows-services/first.pid').write_text('1001')
    (tmp_path/'logs/windows-services/second.pid').write_text('1002')
    fixture=tmp_path/'preflight.ps1'
    fixture.write_text('''param($Source,$Root,$Hidden)
$ErrorActionPreference='Stop'
. $Source
function Get-DepoServicePython { param($Root,$ServiceId,$Mode) 'C:\\fixture\\python.exe' }
$snapshot=@([pscustomobject]@{ProcessId=1001;ExecutablePath='C:\\fixture\\python.exe';CommandLine='python -m first.service'},
  [pscustomobject]@{ProcessId=1002;ExecutablePath=$(if($Hidden -eq 'true'){''}else{'C:\\fixture\\python.exe'});CommandLine='python -m second.service'})
Assert-DepoTrackedServiceIdentities -Root $Root -Snapshot $snapshot
Write-Output 'CHECKED_ALL'
''')
    result=subprocess.run([shell,'-NoProfile','-ExecutionPolicy','Bypass','-File',str(fixture),
          '-Source',str(ROOT/'infra/windows/process-control.ps1'),'-Root',str(tmp_path),'-Hidden',str(hidden).lower()],
          capture_output=True,text=True,timeout=30)
    assert (result.returncode==0)==valid,result.stdout+result.stderr
    assert len(list((tmp_path/'logs/windows-services').glob('*.pid')))==2
    assert not list((tmp_path/'logs/windows-services').glob('*.request'))
    if hidden:assert 'No stop requests were sent' in result.stderr


def test_stop_batch_preflight_precedes_graceful_requests():
    source=(ROOT/'infra/windows/stop-depo-services.ps1').read_text(encoding='utf-8-sig')
    assert source.index('Assert-DepoTrackedServiceIdentities') < source.index('Set-Content')
