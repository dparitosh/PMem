"""Real stdio session reuse, scope isolation and uncertain-call failure handling."""
import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest
from backend.agentic_service import mcp_transport as mcp
from backend.depo_platform.operations import OperationContext, operation_scope

SERVER = '''import sys,json,time,os
count=0
for line in sys.stdin:
    message=json.loads(line)
    if 'id' not in message: continue
    if message['method']=='initialize':
        result={'protocolVersion':'2025-06-18','capabilities':{'tools':{}}}
    else:
        count+=1
        if message.get('params',{}).get('name')=='hang': time.sleep(30)
        result={'count':count,'pid':os.getpid()}
    print(json.dumps({'jsonrpc':'2.0','id':message['id'],'result':result}),flush=True)
'''


def context():
    return OperationContext('same-public-id', (datetime.now(timezone.utc)+timedelta(seconds=30)).isoformat())


def test_session_reuse_isolated_scope_and_shutdown(tmp_path):
    path=tmp_path/'server.py'; path.write_text(SERVER)
    server={'transport':'stdio','command':sys.executable,'args':[str(path)]}
    async def scenario():
        mcp.start_pool()
        processes=[]
        try:
            with operation_scope(context()):
                first=await mcp.invoke(server,'tools/call',{'name':'ok'})
                second=await mcp.invoke(server,'tools/call',{'name':'ok'})
            assert (first['count'],second['count'])==(1,2)
            assert first['pid']==second['pid']
            with operation_scope(context()):
                other=await mcp.invoke(server,'tools/call',{'name':'ok'})
            assert other['count']==1 and other['pid']!=first['pid']
            processes.extend(s['process'] for s in mcp._pools[asyncio.get_running_loop()]['sessions'].values())
        finally:
            await mcp.close_pool()
        assert all(p.returncode is not None for p in processes)
    asyncio.run(scenario())


def test_timeout_evicts_session_without_replaying_call(tmp_path):
    path=tmp_path/'server.py'; path.write_text(SERVER)
    server={'transport':'stdio','command':sys.executable,'args':[str(path)]}
    async def scenario():
        mcp.start_pool()
        try:
            with operation_scope(context()):
                first=await mcp.invoke(server,'tools/call',{'name':'ok'})
                with pytest.raises(TimeoutError):
                    await mcp.invoke(server,'tools/call',{'name':'hang'},timeout_seconds=.05)
                assert not mcp._pools[asyncio.get_running_loop()]['sessions']
                recovered=await mcp.invoke(server,'tools/call',{'name':'ok'})
                assert recovered['pid']!=first['pid'] and recovered['count']==1
        finally:
            await mcp.close_pool()
    asyncio.run(scenario())


def test_idle_session_is_reaped(tmp_path,monkeypatch):
    monkeypatch.setenv('AGENTIC_MCP_IDLE_SECONDS','1')
    path=tmp_path/'server.py'; path.write_text(SERVER)
    server={'transport':'stdio','command':sys.executable,'args':[str(path)]}
    async def scenario():
        mcp.start_pool()
        try:
            with operation_scope(context()):
                await mcp.invoke(server,'tools/call',{'name':'ok'})
            pool=mcp._pools[asyncio.get_running_loop()]
            process=next(iter(pool['sessions'].values()))['process']
            for _ in range(25):
                if process.returncode is not None: break
                await asyncio.sleep(.1)
            assert process.returncode is not None and not pool['sessions']
        finally:
            await mcp.close_pool()
    asyncio.run(scenario())


def test_busy_pool_rejects_before_dispatch_and_cancellation_reaps_child(tmp_path,monkeypatch):
    monkeypatch.setenv('AGENTIC_MCP_MAX_SESSIONS','1')
    path=tmp_path/'server.py'; path.write_text(SERVER)
    server={'transport':'stdio','command':sys.executable,'args':[str(path)]}
    async def scenario():
        mcp.start_pool()
        pending=None
        try:
            with operation_scope(context()):
                await mcp.invoke(server,'tools/call',{'name':'ok'})
                pending=asyncio.create_task(mcp.invoke(server,'tools/call',{'name':'hang'}))
                pool=mcp._pools[asyncio.get_running_loop()]
                session=next(iter(pool['sessions'].values()))
                for _ in range(20):
                    if session['lock'].locked(): break
                    await asyncio.sleep(.01)
                assert session['lock'].locked()
                process=session['process']
            with operation_scope(context()):
                with pytest.raises(RuntimeError,match='capacity is busy'):
                    await mcp.invoke(server,'tools/call',{'name':'ok'})
            pending.cancel()
            await asyncio.gather(pending,return_exceptions=True)
            assert process.returncode is not None
            assert not pool['sessions']
        finally:
            if pending is not None and not pending.done():
                pending.cancel(); await asyncio.gather(pending,return_exceptions=True)
            await mcp.close_pool()
    asyncio.run(scenario())
