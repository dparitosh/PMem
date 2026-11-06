import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from backend.agentic_service.mcp_transport import invoke
from backend.depo_platform.operations import OperationContext, operation_scope


SERVER = '''import sys,json
for line in sys.stdin:
    request=json.loads(line)
    if 'id' not in request: continue
    if request['method']=='initialize':
        result={'protocolVersion':'2025-06-18','capabilities':{'tools':{}}}
    else:
        token=request['params']['_meta']['progressToken']
        print(json.dumps({'jsonrpc':'2.0','method':'notifications/progress','params':{'progressToken':token,'progress':1,'total':2,'message':'private text'}}),flush=True)
        result={'content':[]}
    print(json.dumps({'jsonrpc':'2.0','id':request['id'],'result':result}),flush=True)
'''


class ProgressTests(unittest.TestCase):
    def test_stdio_progress_is_numeric_and_retained(self):
        async def run(path):
            progress=[]
            async def retain(value): progress.append(value)
            context=OperationContext('test', (datetime.now(timezone.utc)+timedelta(seconds=10)).isoformat(), retain)
            with operation_scope(context):
                result=await invoke({'transport':'stdio','command':'python','args':[str(path)]},'tools/call',{'name':'test','arguments':{}})
            self.assertEqual(result, {'content':[]})
            self.assertEqual(progress, [{'current':1,'total':2,'source':'mcp'}])
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'server.py'
            path.write_text(SERVER, encoding='utf-8')
            asyncio.run(run(path))
