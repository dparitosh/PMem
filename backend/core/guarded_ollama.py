"""Keep LangChain composition while applying the shared Ollama admission policy."""
from langchain_core.runnables import Runnable
from langchain_core.embeddings import Embeddings
from .ollama_limits import request_slot, request_slot_sync
from .ollama_auth import ollama_headers


class GuardedOllama(Runnable):
    def __init__(self, model, endpoint): self.model, self.endpoint = model, endpoint

    def invoke(self, input, config=None, **kwargs):
        ollama_headers(self.endpoint)
        with request_slot_sync(self.endpoint): return self.model.invoke(input, config=config, **kwargs)

    async def ainvoke(self, input, config=None, **kwargs):
        ollama_headers(self.endpoint)
        async with request_slot(self.endpoint): return await self.model.ainvoke(input, config=config, **kwargs)

    def stream(self, input, config=None, **kwargs):
        ollama_headers(self.endpoint)
        with request_slot_sync(self.endpoint): yield from self.model.stream(input, config=config, **kwargs)

    async def astream(self, input, config=None, **kwargs):
        ollama_headers(self.endpoint)
        async with request_slot(self.endpoint):
            async for value in self.model.astream(input, config=config, **kwargs): yield value

    def bind_tools(self, *args, **kwargs):
        return GuardedOllama(self.model.bind_tools(*args, **kwargs), self.endpoint)

    def with_structured_output(self, *args, **kwargs):
        return GuardedOllama(self.model.with_structured_output(*args, **kwargs), self.endpoint)


class GuardedEmbeddings(Embeddings):
    def __init__(self, model, endpoint): self.model, self.endpoint = model, endpoint

    def embed_documents(self, texts, **kwargs):
        ollama_headers(self.endpoint)
        with request_slot_sync(self.endpoint): return self.model.embed_documents(texts, **kwargs)

    def embed_query(self, text, **kwargs):
        ollama_headers(self.endpoint)
        with request_slot_sync(self.endpoint): return self.model.embed_query(text, **kwargs)

    async def aembed_documents(self, texts, **kwargs):
        ollama_headers(self.endpoint)
        async with request_slot(self.endpoint): return await self.model.aembed_documents(texts, **kwargs)

    async def aembed_query(self, text, **kwargs):
        ollama_headers(self.endpoint)
        async with request_slot(self.endpoint): return await self.model.aembed_query(text, **kwargs)
