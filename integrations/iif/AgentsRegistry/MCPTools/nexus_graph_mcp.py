"""Dependency-free stdio MCP bridge for the existing fixed-intent IIF tool.

No model arguments, credential inputs, graph writes, sampling or delegated roots.
Business logic and authority stay in CodedTools and the Graph microservice.
"""
import json
import sys
from pathlib import Path

# Support direct script launch from any controller working directory.
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from AgentsRegistry.CodedTools.nexus_graph import compute_selected_graph

VERSIONS={'2024-11-05','2025-03-26','2025-06-18'}
TOOL={'name':'compute_selected_graph','description':'Read graph computation evidence for the operator-owned intent.',
      'inputSchema':{'type':'object','properties':{},'additionalProperties':False},
      'annotations':{'readOnlyHint':True,'destructiveHint':False}}

def handle(message):
    identifier=message.get('id') if isinstance(message,dict) else None
    def error(code,text):return {'jsonrpc':'2.0','id':identifier,'error':{'code':code,'message':text}}
    if not isinstance(message,dict) or message.get('jsonrpc')!='2.0':return error(-32600,'Invalid MCP request')
    if 'id' not in message:return None
    method=message.get('method');params=message.get('params',{})
    if not isinstance(params,dict):return error(-32602,'MCP parameters must be an object')
    if method=='initialize':
        version=params.get('protocolVersion')
        if version not in VERSIONS:return error(-32602,'Unsupported MCP protocol version')
        result={'protocolVersion':version,'capabilities':{'tools':{}},'serverInfo':{'name':'NEXUS scoped graph computation','version':'1.0.0'}}
    elif method=='ping':result={}
    elif method=='tools/list':result={'tools':[TOOL]}
    elif method=='tools/call':
        if params.get('name')!=TOOL['name']:return error(-32601,'Unknown graph tool')
        if not isinstance(params.get('arguments',{}),dict) or params.get('arguments'):return error(-32602,'Graph intent is operator-owned; this tool takes no arguments')
        try:result={'content':[{'type':'text','text':json.dumps(compute_selected_graph())}]}
        except Exception as failure:
            result={'isError':True,'content':[{'type':'text','text':str(failure)[:300]}]}
    else:return error(-32601,'MCP method not supported')
    return {'jsonrpc':'2.0','id':identifier,'result':result}

def main():
    while True:
        line=sys.stdin.buffer.readline(65537)
        if not line:return
        if len(line)>65536:return
        try:response=handle(json.loads(line))
        except (ValueError,TypeError):response={'jsonrpc':'2.0','id':None,'error':{'code':-32700,'message':'Invalid JSON request'}}
        if response is not None:
            sys.stdout.buffer.write(json.dumps(response).encode('utf-8')+b'\n');sys.stdout.buffer.flush()

if __name__=='__main__':main()
