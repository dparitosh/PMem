import ast
import base64
import binascii
import copy
import json
import os
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch


class Failure(Exception):
    def __init__(self, status, detail): self.status_code, self.detail = status, detail


class AttachmentBindingTests(unittest.IsolatedAsyncioTestCase):
    async def exercise(self, attachment):
        observed = {}
        tool = {'id':'upload', 'input_kind':'multipart', 'input_schema':{'type':'object','properties':{'file':{'type':'object'},'form':{'type':'object'}},'required':['file']}}
        agent = {'id':'parser','tools':['upload']}
        async def selected(tools, request): return copy.deepcopy(tools)
        async def suggest(agent, tools, task, **kw):
            observed.update(tools=tools, prompt=kw)
            return {'tool_id':'upload','inputs':{'form':{}}}
        async def preflight(commands, request): observed['command'] = copy.deepcopy(commands[0])
        async def io(fn, *args): return fn(*args)
        scope = {'__name__':'backend.agentic_service.router', '__package__':'backend.agentic_service', 'Any':object,'Request':object,'HTTPException':Failure,'httpx':SimpleNamespace(HTTPError=OSError),
                 'base64':base64,'binascii':binascii,'os':os,'json':json,
                 'catalog':SimpleNamespace(item=lambda kind, key: agent if kind == 'agents' else tool),
                 '_proposal_tools':selected,'_preflight_tools':preflight,'_agent_io':io,
                 'plan':lambda command:{'requires_approval':True},'graph_read_identity':lambda req:'actor',
                 'sessions':SimpleNamespace(owner=lambda *args:'owner'),
                 'recommendations':SimpleNamespace(create=lambda result, owner:result)}
        tree = ast.parse(Path('backend/agentic_service/router.py').read_text(encoding='utf-8'))
        nodes = [node for node in tree.body if getattr(node,'name','') in {'_multipart','suggest_agent_tool'}]
        for node in nodes: node.decorator_list = []
        exec(compile(ast.Module(body=nodes,type_ignores=[]),'<attachment>','exec'),scope)
        model = ModuleType('backend.agentic_service.local_llm'); model.suggest_tool = suggest
        with patch.dict(sys.modules, {'backend.agentic_service.local_llm':model}):
            result = await scope['suggest_agent_tool']('parser', {'task':'Import source','context':{'page':'data-flow'},**({'attachment':attachment} if attachment else {})}, object())
        return result, observed

    async def test_real_bytes_are_bound_after_model_proposal(self):
        attachment = {'filename':'source.ttl','content_base64':base64.b64encode(b'real source bytes').decode()}
        result, observed = await self.exercise(attachment)
        self.assertEqual(result['command']['inputs']['file'], attachment)
        self.assertNotIn('file', observed['tools'][0]['input_schema']['properties'])
        self.assertNotIn('content_base64', json.dumps(observed['prompt']))
        self.assertEqual(result['context'], {'page':'data-flow'})

    async def test_upload_only_agent_requires_a_real_attachment(self):
        with self.assertRaises(Failure) as error: await self.exercise(None)
        self.assertEqual(error.exception.status_code, 422)
