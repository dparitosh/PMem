import asyncio
import logging
import sys

import pytest

from backend.agentic_service.mcp_transport import invoke


def test_failed_child_stderr_is_drained_and_only_categories_are_logged(caplog):
    server = {'transport': 'stdio', 'command': sys.executable, 'args': ['-c',
        "import sys; sys.stderr.write('x'*100000+'\\nModuleNotFoundError: fixture-secret-value\\n'); sys.stderr.flush(); sys.exit(1)"]}
    with caplog.at_level(logging.INFO, logger='backend.agentic_service.mcp_transport'):
        with pytest.raises((ValueError, BrokenPipeError, ConnectionResetError)):
            asyncio.run(invoke(server, 'tools/list', timeout_seconds=5))
    assert 'missing-module' in caplog.text
    assert 'stderr_bytes=' in caplog.text
    assert 'fixture-secret-value' not in caplog.text


def test_child_receives_runtime_home_paths_but_not_unlisted_credentials(monkeypatch):
    monkeypatch.setenv('USERPROFILE',r'C:\Users\Operator')
    monkeypatch.setenv('UNLISTED_CUSTOMER_SECRET','must-not-cross')
    code="""import sys,json,os
for line in sys.stdin:
 m=json.loads(line)
 if 'id' not in m:continue
 result={'protocolVersion':'2025-06-18','capabilities':{'tools':{}}} if m['method']=='initialize' else {'profile':os.getenv('USERPROFILE'),'secret_forwarded':'UNLISTED_CUSTOMER_SECRET' in os.environ}
 print(json.dumps({'jsonrpc':'2.0','id':m['id'],'result':result}),flush=True)
"""
    result=asyncio.run(invoke({'transport':'stdio','command':sys.executable,'args':['-c',code]},'tools/call',{'name':'runtime-check'},timeout_seconds=5))
    assert result['profile']==r'C:\Users\Operator'
    assert result['secret_forwarded'] is False
