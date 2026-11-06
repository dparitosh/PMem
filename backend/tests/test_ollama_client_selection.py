import ast
import unittest
from pathlib import Path
from unittest.mock import patch
from backend.core.ollama_auth import ollama_base_url, ollama_headers

class ClientSelection(unittest.TestCase):
    def factories(self):
        tree=ast.parse(Path('backend/core/llm.py').read_text(encoding='utf-8'))
        names={'_init_ollama_llm','_init_unstructured_ollama_llm','_init_ollama_tool_llm'}
        nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names]
        class Chat:
            def __init__(self,**kw): self.settings=kw
            def bind_tools(self,tools): return self
        class Generate:
            def __init__(self,**kw): self.settings=kw
        ns={'ChatOllama':Chat,'OllamaLLM':Generate,'OLLAMA_BASE_URL':'http://custom', 'LLM_MODEL_NAME':'test',
            'OLLAMA_API_KEY':'fixture','UNSTRUCTURED_OLLAMA_BASE_URL':'http://custom/api/generate',
            'UNSTRUCTURED_LLM_MODEL_NAME':'documents','UNSTRUCTURED_OLLAMA_API_KEY':'fixture',
            'ollama_base_url':ollama_base_url,'_normalize_ollama_base_url':ollama_base_url,'ollama_timeout':lambda:30,'ollama_headers':ollama_headers}
        exec(compile(ast.Module(body=nodes,type_ignores=[]),'<actual factories>','exec'),ns)
        return ns,Chat,Generate

    def test_generation_and_tool_chat_are_distinct_clients(self):
        ns,Chat,Generate=self.factories()
        with patch.dict('os.environ',{'OLLAMA_API_URL':'http://custom/api/generate','OLLAMA_CHAT_API_URL':'http://tools/api/chat'},clear=True):
            self.assertIsInstance(ns['_init_ollama_llm'](),Generate)
            self.assertIsInstance(ns['_init_unstructured_ollama_llm'](),Generate)
            tools=ns['_init_ollama_tool_llm']()
            self.assertIsInstance(tools,Chat)
            self.assertEqual(tools.settings['base_url'],'http://tools')
            self.assertFalse(tools.settings['client_kwargs']['trust_env'])
            self.assertEqual(tools.settings['client_kwargs']['headers'],{'api-key':'fixture'})
            self.assertIs(tools.bind_tools([]),tools)

    def test_chat_configuration_preserves_chat_client(self):
        ns,Chat,Generate=self.factories()
        ns['UNSTRUCTURED_OLLAMA_BASE_URL']='http://custom/api/chat'
        with patch.dict('os.environ',{'OLLAMA_API_URL':'http://custom/api/chat'},clear=True):
            self.assertIsInstance(ns['_init_ollama_llm'](),Chat)
            self.assertIsInstance(ns['_init_unstructured_ollama_llm'](),Chat)

if __name__=='__main__': unittest.main()
