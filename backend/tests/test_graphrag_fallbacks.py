from types import ModuleType, SimpleNamespace
import importlib
import sys

from langchain_core.documents import Document


class _FakeRetriever:
    def invoke(self, payload):
        return {
            "context": [
                Document(
                    page_content="Chunk about requirement traceability",
                    metadata={"node_id": "chunk-1"},
                )
            ]
        }


class _FakeQAChain:
    def invoke(self, payload):
        return "Grounded graph answer"


def _load_vector_module(monkeypatch):
    fake_llm = ModuleType("core.llm")
    fake_llm.llm = None
    fake_llm.embeddings = None
    fake_llm.LLM_AVAILABLE = False
    fake_llm.EMBEDDER_AVAILABLE = False

    fake_graph = ModuleType("core.graph")
    fake_graph.graph = SimpleNamespace(query=lambda *args, **kwargs: [])

    fake_langchain_neo4j = ModuleType("langchain_neo4j")
    fake_langchain_neo4j.Neo4jVector = object

    fake_langchain_chains = ModuleType("langchain.chains")
    fake_langchain_combine = ModuleType("langchain.chains.combine_documents")
    fake_langchain_stuff = ModuleType("langchain.chains.combine_documents.stuff")
    fake_langchain_stuff.create_stuff_documents_chain = lambda *args, **kwargs: None
    fake_langchain_chains.create_retrieval_chain = lambda *args, **kwargs: None

    monkeypatch.setitem(sys.modules, "core.llm", fake_llm)
    monkeypatch.setitem(sys.modules, "backend.core.llm", fake_llm)
    monkeypatch.setitem(sys.modules, "core.graph", fake_graph)
    monkeypatch.setitem(sys.modules, "backend.core.graph", fake_graph)
    monkeypatch.setitem(sys.modules, "langchain_neo4j", fake_langchain_neo4j)
    monkeypatch.setitem(sys.modules, "langchain.chains", fake_langchain_chains)
    monkeypatch.setitem(sys.modules, "langchain.chains.combine_documents", fake_langchain_combine)
    monkeypatch.setitem(sys.modules, "langchain.chains.combine_documents.stuff", fake_langchain_stuff)

    import backend.chains.vector as vector_module
    return importlib.reload(vector_module)


def _load_chat_module(monkeypatch):
    fake_vector = ModuleType("chains.vector")
    fake_vector.get_data_info = lambda query, labels=None, k=5: {"answer": "doc", "context": []}
    fake_vector.deep_vector_search = lambda query: {"answer": "fallback", "context": []}

    fake_cypher = ModuleType("chains.cypher")
    fake_cypher.cypher_qa = None

    fake_memory = ModuleType("agent.memory")
    fake_memory.get_memory = lambda session_id=None: []

    fake_llm = ModuleType("core.llm")
    fake_llm.llm = None
    fake_llm.LLM_AVAILABLE = False

    monkeypatch.setitem(sys.modules, "chains.vector", fake_vector)
    monkeypatch.setitem(sys.modules, "chains.cypher", fake_cypher)
    monkeypatch.setitem(sys.modules, "agent.memory", fake_memory)
    monkeypatch.setitem(sys.modules, "core.llm", fake_llm)
    monkeypatch.setitem(sys.modules, "backend.core.llm", fake_llm)

    import backend.agent.chat as chat_module
    return importlib.reload(chat_module)


def test_deep_vector_search_uses_chunk_node_id_property(monkeypatch):
    vector = _load_vector_module(monkeypatch)
    captured = {}

    def fake_query(query, params=None):
        captured["query"] = query
        captured["params"] = params
        return []

    monkeypatch.setattr(vector, "general_retrieval_chain", _FakeRetriever())
    monkeypatch.setattr(vector, "general_qa_chain", _FakeQAChain())
    monkeypatch.setattr(vector, "graph", SimpleNamespace(query=fake_query))

    result = vector.deep_vector_search("REQ-0001")

    assert captured["params"] == {"node_ids": ["chunk-1"]}
    assert "toString(a.node_id) = node_id" in captured["query"]
    assert result["answer"] == "Grounded graph answer"
    assert result["context"]


def test_graph_context_search_falls_back_to_vector_when_graph_context_empty(monkeypatch):
    chat = _load_chat_module(monkeypatch)

    fake_graph_view = ModuleType("backend.Services.graph_view_service")

    class FakeGraphViewService:
        @staticmethod
        def get_contextual_subgraph(**kwargs):
            return {"nodes": [], "relationships": [], "counts": {"nodes": 0, "relationships": 0}}

    fake_graph_view.GraphViewService = FakeGraphViewService
    monkeypatch.setitem(sys.modules, "backend.Services.graph_view_service", fake_graph_view)
    monkeypatch.setattr(
        chat,
        "deep_vector_search",
        lambda query: {
            "answer": "Fallback vector result",
            "context": [Document(page_content="Fallback context", metadata={"source": "vector"})],
        },
    )

    result = chat.graph_context_search.func("ontology requirement traceability")

    assert "Fallback vector result" in result
    assert "Fallback context" in result
