import json, shutil, subprocess
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[2]
NODE=Path(r'D:\GenAI_Projects\NodeJS\node.exe')


def test_frontend_locked_dependency_probe_detects_missing_and_changed_versions(tmp_path):
    if not NODE.exists():pytest.skip('Node runtime unavailable')
    shutil.copy(ROOT/'frontend/checkDependencies.mjs',tmp_path/'checkDependencies.mjs')
    (tmp_path/'package.json').write_text(json.dumps({'dependencies':{'example':'1.0.0'}}))
    (tmp_path/'package-lock.json').write_text(json.dumps({'packages':{'node_modules/example':{'version':'1.0.0'}}}))
    def probe():
        r=subprocess.run([str(NODE),str(tmp_path/'checkDependencies.mjs')],capture_output=True,text=True)
        assert r.returncode==0,r.stderr
        return json.loads(r.stdout)
    assert probe()=={'current':False,'mismatches':['example']}
    package=tmp_path/'node_modules/example';package.mkdir(parents=True)
    (package/'package.json').write_text('{"version":"1.0.0"}')
    assert probe()=={'current':True,'mismatches':[]}
    (package/'package.json').write_text('{"version":"0.9.0"}')
    assert probe()['current'] is False


def test_upgrade_enables_checkpointed_installer_before_shutdown(tmp_path):
    shell=shutil.which('powershell.exe')
    if not shell:pytest.skip('Windows PowerShell unavailable')
    text=(ROOT/'infra/windows/update-depo-windows.ps1').read_text(encoding='utf-8')
    begin=text.index('# Detect changed locked frontend dependencies')
    end=text.index('if ($EnableOcr',begin)
    assert end<text.index("Write-Host 'Read-only database upgrade checks passed")
    frontend=tmp_path/'frontend';frontend.mkdir()
    (frontend/'checkDependencies.mjs').write_text('console.log(JSON.stringify({current:false,mismatches:["example"]}))')
    script=tmp_path/'probe.ps1'
    script.write_text("$ErrorActionPreference='Stop'\n$root='"+str(tmp_path)+"'\n$settings=@{}\n$SkipFrontend=$false\n$InstallDependencies=$false\nfunction Invoke-DepoUpgradeStep($Name,$Action){& $Action}\nfunction Get-DepoNodeRuntime {return @{Node='"+str(NODE)+"'}}\n"+text[begin:end]+"\nif(!$InstallDependencies){throw 'Installer not enabled'}\n",encoding='utf-8')
    r=subprocess.run([shell,'-NoProfile','-ExecutionPolicy','Bypass','-File',str(script)],capture_output=True,text=True)
    assert r.returncode==0,r.stdout+r.stderr
