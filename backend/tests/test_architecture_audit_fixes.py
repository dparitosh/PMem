"""Regression tests for queue ownership, recovery and paginated MCP discovery."""
import asyncio
import subprocess
import sys
from pathlib import Path

import pytest
from backend.qif.ownership import queue_owner
from backend.qif.task_service import QifTaskService
from backend.agentic_service.mcp_transport import invoke


def test_queue_owner_rejects_second_process_and_releases_on_exit(tmp_path):
    script = "from pathlib import Path; from backend.qif.ownership import queue_owner; import sys;\nwith queue_owner(Path(sys.argv[1])): pass"
    with queue_owner(tmp_path):
        result = subprocess.run([sys.executable, '-c', script, str(tmp_path)], capture_output=True, timeout=10)
        assert result.returncode != 0
        assert b'already has an owner' in result.stderr
    result = subprocess.run([sys.executable, '-c', script, str(tmp_path)], capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr


def test_recovery_does_not_depend_on_recent_history_page(tmp_path, monkeypatch):
    service = QifTaskService(tmp_path)
    try:
        task = service.create(source_paths=[], ontology_name='test', prefix='test', description='', source='test')
        monkeypatch.setattr(service, 'list', lambda **kw: [])
        resumed = []
        monkeypatch.setattr(service, 'submit_prepare', lambda identity: resumed.append(identity))
        assert service.recover_pending()['recovered'] == 1
        assert resumed == [task['task_id']]
    finally:
        service.shutdown()


@pytest.mark.parametrize('looping', [False, True])
def test_mcp_discovery_collects_pages_in_one_process_and_rejects_cursor_cycles(tmp_path, looping):
    program = tmp_path / 'mcp_server.py'
    program.write_text('''import json, sys
for line in sys.stdin:
    m=json.loads(line)
    if 'id' not in m: continue
    if m['method']=='initialize':
        result={'protocolVersion':'2025-06-18','capabilities':{'tools':{}}}
    elif m.get('params',{}).get('cursor'):
        result={'tools':[{'name':'second','inputSchema':{'type':'object'}}]}
        if LOOPING: result['nextCursor']='next'
    else:
        result={'tools':[{'name':'first','inputSchema':{'type':'object'}}],'nextCursor':'next'}
    print(json.dumps({'jsonrpc':'2.0','id':m['id'],'result':result}),flush=True)
'''.replace('LOOPING', repr(looping)))
    server = {'transport':'stdio','command':sys.executable,'args':[str(program)]}
    if looping:
        with pytest.raises(ValueError, match='pagination'):
            asyncio.run(invoke(server, 'tools/list', timeout_seconds=5))
    else:
        result = asyncio.run(invoke(server, 'tools/list', timeout_seconds=5))
        assert [row['name'] for row in result['tools']] == ['first','second']
        assert 'nextCursor' not in result


def test_qif_registration_requires_no_peer_filesystem_path(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from backend.qif import task_service as module
    service = QifTaskService(tmp_path)
    try:
        task = service.create(source_paths=[], ontology_name='test', prefix='test', description='', source='test')
        identity = task['task_id']
        artifact_dir = tmp_path / identity / 'ontology'
        artifact_dir.mkdir()
        (artifact_dir / 'test_qif_ontology.ttl').write_text('@prefix : <urn:test:> .')
        service._update(identity, status='awaiting_approval')
        publisher = SimpleNamespace(register=lambda **kw: {'status':'success','ontology_id':'remote'},
                                    sync_graph=lambda **kw: {'status':'success'})
        monkeypatch.setattr(module, 'get_publisher', lambda: publisher)
        service.commit(identity)
        assert service.get(identity)['status'] == 'completed'
        assert service.get(identity)['ontology_id'] == 'remote'
    finally:
        service.shutdown()
