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


def test_upgrade_reconciles_all_dependency_locks_by_default(tmp_path):
    shell=shutil.which('powershell.exe')
    if not shell:pytest.skip('Windows PowerShell unavailable')
    import os
    env={**os.environ,'TEMP':str(tmp_path),'TMP':str(tmp_path)}
    # Windows PowerShell must load its own Security module, not a module path
    # inherited from a PowerShell 7 test runner.
    env['PSModulePath']=str(Path(shell).parent/'Modules')
    r=subprocess.run([shell,'-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'infra/windows/test-depo-update.ps1')],capture_output=True,text=True,env=env,timeout=60)
    assert r.returncode==0,r.stdout+r.stderr
