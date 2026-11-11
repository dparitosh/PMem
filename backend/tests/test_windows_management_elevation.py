"""Exercise UAC preflight with fake process records; never stop a real process."""
import json
import shutil
import subprocess
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[2]
SHELL=shutil.which('powershell.exe')

@pytest.mark.skipif(not SHELL,reason='Windows PowerShell required')
@pytest.mark.parametrize('mode',['visible','hidden','elevated','cancelled','failed','retry'])
def test_lifecycle_visibility_is_resolved_before_process_control(tmp_path,mode):
 script=tmp_path/'fixture.ps1'
 script.write_text(r'''param($Repository,$Fixture,$Mode)
$ErrorActionPreference='Stop'
. (Join-Path $Repository 'infra/windows/process-control.ps1')
$tracking=Join-Path $Fixture 'logs/windows-services'
New-Item -ItemType Directory -Path $tracking -Force | Out-Null
Set-Content -LiteralPath (Join-Path $tracking 'frontend.pid') -Value '5068'
$script:invocations=0
$script:command=''
function Get-CimInstance {if($Mode -eq 'visible'){[pscustomobject]@{ProcessId=5068;ExecutablePath='C:/fixture/python.exe';CommandLine='unrelated process'}}else{[pscustomobject]@{ProcessId=5068;ExecutablePath=$null;CommandLine=$null}}}
function Test-DepoAdministrator {return ($Mode -eq 'elevated')}
function Start-Process {
 param($FilePath,$Verb,$WindowStyle,[switch]$Wait,[switch]$PassThru,$ArgumentList,$ErrorAction)
 $script:invocations++
 if($Verb -ne 'RunAs' -or $WindowStyle -ne 'Hidden' -or $Wait){throw 'Invalid elevation flow'}
 $script:command=[Text.Encoding]::Unicode.GetString([Convert]::FromBase64String($ArgumentList[-1]))
 if($Mode -eq 'cancelled'){throw 'UAC cancelled'}
 $process=[pscustomobject]@{ExitCode=$(if($Mode -eq 'failed'){7}else{0})}
 $process | Add-Member -MemberType ScriptMethod -Name WaitForExit -Value {$script:waitedForRoot=$true}
 $process
}
$failure='';$result=$false
try {$result=Invoke-DepoVisibleManagement -Root $Fixture -Action Restart -EnvFile "configuration's selected.env" -Profile Bootstrap -SkipPostgres -SkipBaselineProvisioning -ElevatedRetry:($Mode -eq 'retry')}
catch {$failure=$_.Exception.Message}
@{result=$result;failure=$failure;invocations=$script:invocations;command=$script:command;waitedForRoot=$script:waitedForRoot;trackingRetained=(Test-Path -LiteralPath (Join-Path $tracking 'frontend.pid'))} | ConvertTo-Json -Compress
''',encoding='utf-8')
 response=subprocess.run([SHELL,'-NoProfile','-ExecutionPolicy','Bypass','-File',str(script),str(ROOT),str(tmp_path),mode],capture_output=True,text=True,timeout=30)
 assert response.returncode==0,response.stderr
 value=json.loads(response.stdout.strip().splitlines()[-1])
 assert value['trackingRetained']
 if mode=='visible':
  assert not value['result'] and value['invocations']==0 and not value['failure']
 elif mode in {'elevated','retry'}:
  assert value['invocations']==0 and 'No lifecycle action was started' in value['failure']
 elif mode=='cancelled':
  assert value['invocations']==1 and 'cancelled or unavailable' in value['failure']
 elif mode=='failed':
  assert value['invocations']==1 and 'elevated PMem lifecycle command failed' in value['failure']
 else:
  assert value['result'] and not value['failure'] and value['invocations']==1 and value['waitedForRoot']
  assert "configuration''s selected.env'" in value['command']
  assert '-SkipPostgres' in value['command'] and '-SkipBaselineProvisioning' in value['command']
  assert '-ElevatedRetry' in value['command'] and "-Action 'Restart'" in value['command']


def test_preflight_precedes_any_stop_or_start():
 source=(ROOT/'manage-depo.ps1').read_text()
 assert source.index('Invoke-DepoVisibleManagement')<source.index('function Invoke-ManagedStep')
 source=(ROOT/'infra/windows/stop-depo-frontend.ps1').read_text()
 assert source.index('Windows did not expose the identity')<source.index('if ($recorded -and -not (Test-ProjectFrontend')
