import os
import logging
from backend.core.llm import llm, embeddings, LLM_AVAILABLE, EMBEDDER_AVAILABLE
from backend.core.graph import graph
from langchain_neo4j import Neo4jVector
from langchain_core.prompts import ChatPromptTemplate
from langchain.chains.combine_documents.stuff import create_stuff_documents_chain
from typing import Optional, List, Dict, Any
from langchain_core.documents import Document

logger = logging.getLogger(__name__)

GRAPH_VECTOR_INDEX = os.getenv("NEO4J_GRAPH_VECTOR_INDEX", "graph_embedding")
GRAPH_KEYWORD_INDEX = os.getenv("NEO4J_GRAPH_KEYWORD_INDEX", "keyword_index")
DATASHEET_VECTOR_INDEX = os.getenv("NEO4J_DATASHEET_VECTOR_INDEX", "datasheet_index")
DATASHEET_KEYWORD_INDEX = os.getenv("NEO4J_DATASHEET_KEYWORD_INDEX", "datasheetkeyword")

# --- Prompts (always safe to define) ---
data_prompt = ChatPromptTemplate.from_messages([
    ("system", """You are a graph database assistant.
     Answer the question using the provided context, which contains multiple documents information.
     These are in markdown format, understand the format and give answer after converting markdown to its intended format.
     Understand the question and context and give accurate answers.
     If the answer cannot be reasonably inferred from the context, respond honestly and say so instead of guessing.

Context: {context}"""),
    ("human", "{input}")
])

general_prompt = ChatPromptTemplate.from_messages([
    ("system", """You are a graph database assistant. Answer the question using the provided context, which contains structured summaries of graph nodes and their relationships.


Each item in the context includes:

A node's labels and key-value properties

Relationships between nodes, including type and any properties

Labels indicate the type of node, and relationships show how nodes are connected.

Use this information to infer meaning and answer the question accurately. If the answer cannot be reasonably inferred from the context, respond honestly and say so instead of guessing.

Context: {context}"""),
    ("human", "{input}")
])

# --- Vector stores and chains (only init when LLM + embedder are available) ---
general_vector = None
datasheet_vector = None
datasheet_retriever = None
general_retriever = None
data_qa_chain = None
general_qa_chain = None

import threading
import time
_vector_init_lock = threading.Lock()
_vector_retry_at = 0


def _initialize_vectors():
    global general_vector, general_retriever, general_qa_chain
    global datasheet_vector, datasheet_retriever, data_qa_chain, _vector_retry_at
    if not LLM_AVAILABLE or not EMBEDDER_AVAILABLE or time.monotonic() < _vector_retry_at:
        return
    with _vector_init_lock:
        if time.monotonic() < _vector_retry_at:
            return
        _vector_retry_at = time.monotonic() + 30
        if general_qa_chain is None:
            try:
                general_vector = Neo4jVector.from_existing_index(
                    embeddings,
                    graph=graph,
                    index_name=GRAPH_VECTOR_INDEX,
                    node_label="GraphChunk",
                    text_node_property="content",
                    embedding_node_property="embedding",
                    search_type="hybrid",
                    keyword_index_name=GRAPH_KEYWORD_INDEX,
                    retrieval_query="""
        WITH node, score
        MATCH (node)-[:EMBEDDED_FROM]->(source)
        WHERE NOT source:StagedOntologyResource AND NOT source:RetainedOntologyIdentity AND NOT source:OntologyPublication
        WITH node, score, labels(node) as node_labels
        WITH node, score, node_labels,
             CASE
                 WHEN node.content  IS NOT NULL THEN node.content
                 ELSE 'No content'
             END as display_content
        RETURN
            display_content AS text,
            score,
            {
                node_id: node.node_id,
                source_labels: node.labels_source
            } AS metadata
        """
                )

                general_retriever = general_vector.as_retriever(search_kwargs={"k": 5})
                general_qa_chain = create_stuff_documents_chain(llm, general_prompt)
            except Exception as exc:
                logger.warning("Graph vector initialization unavailable: %s", type(exc).__name__)
        if data_qa_chain is None:
            try:
                datasheet_vector = Neo4jVector.from_existing_index(
                    embeddings,
                    graph=graph,
                    index_name=DATASHEET_VECTOR_INDEX,
                    node_label="DatasheetChunk",
                    text_node_property="content",
                    embedding_node_property="embedding",
                    search_type="hybrid",
                    keyword_index_name=DATASHEET_KEYWORD_INDEX,
                    retrieval_query="""
        WITH node, score
        WITH node, score, labels(node) as node_labels
        WITH node, score, node_labels,
             CASE
                 WHEN node.content  IS NOT NULL THEN node.content
                 ELSE 'No content'
             END as display_content
        RETURN
            display_content AS text,
            score,
            {
                node_id: elementId(node),
                source_labels: labels(node),
                filename: node.filename,
                document_id: node.document_id,
                chunkID: node.chunk_id
            } AS metadata
        """
                )

                datasheet_retriever = datasheet_vector.as_retriever(search_kwargs={"k": 5})
                data_qa_chain = create_stuff_documents_chain(llm, data_prompt)
            except Exception as exc:
                logger.warning("Document vector initialization unavailable: %s", type(exc).__name__)


_initialize_vectors()


def format_graph_context(node_chunks, relationship_data):
    node_texts = [doc.page_content for doc in node_chunks]
    rel_texts = []
    for r in relationship_data:
        rel = r["rel"]
        src_label = (rel["source"].get("labels") or ["Node"])[0]
        tgt_label = (rel["target"].get("labels") or ["Node"])[0]
        rel_props = rel["properties"]
        rel_text = f"{src_label} →[:{rel['type']} {rel_props}]→ {tgt_label}"
        rel_texts.append(rel_text)
    return "\n".join(node_texts + rel_texts)


def _require_general_chain():
    if general_retriever is None or general_qa_chain is None:
        _initialize_vectors()
    if general_retriever is None or general_qa_chain is None:
        raise RuntimeError(
            "Graph vector search is unavailable. Check backend logs and ensure the graph retriever and LLM are reachable."
        )


def deep_vector_search(input: str):
    _require_general_chain()
    node_chunks = general_retriever.invoke(input)
    node_results = {"answer":"No matching graph evidence was found.", "context":node_chunks}
    if not node_chunks:
        return node_results

    node_ids = [
        str(doc.metadata.get("node_id")).strip()
        for doc in node_chunks
        if getattr(doc, "metadata", None) and doc.metadata.get("node_id") not in (None, "")
    ]
    if not node_ids:
        return node_results

    rel_query = """
    MATCH (chunk:GraphChunk)-[:EMBEDDED_FROM]->(a)-[r]-(b)
    WHERE toString(chunk.node_id) IN $node_ids
      AND NOT b:GraphChunk AND NOT b:DatasheetChunk
      AND NOT a:StagedOntologyResource AND NOT a:RetainedOntologyIdentity AND NOT a:OntologyPublication
      AND NOT b:StagedOntologyResource AND NOT b:RetainedOntologyIdentity AND NOT b:OntologyPublication
    RETURN DISTINCT {
      type: type(r),
      properties: r{.predicate, .description, .unit, .value},
      source: {
        node_id: elementId(startNode(r)),
        labels: labels(startNode(r)),
        properties: {name:startNode(r).name, label:startNode(r).label, iri:startNode(r).iri}
      },
      target: {
        node_id: elementId(endNode(r)),
        labels: labels(endNode(r)),
        properties: {name:endNode(r).name, label:endNode(r).label, iri:endNode(r).iri}
      }
    } AS rel LIMIT 200
    """

    try:
        relationship_data = graph.query(rel_query, params={"node_ids": node_ids})
    except Exception as exc:
        logger.warning("GraphRAG relationship enrichment failed: %s", exc)
        relationship_data = []

    context = format_graph_context(node_chunks, relationship_data)[:32000]
    docs = [Document(page_content=context)]

    return {
        "answer": general_qa_chain.invoke({"input": input, "context": docs}),
        "context": docs,
    }

def _retrieve_scoped(vector, query, labels, k):
    if not labels:
        return vector.as_retriever(search_kwargs={"k":k}).invoke(query)
    wanted = sorted({str(label).strip().lower() for label in labels if str(label).strip()})
    # Hybrid search cannot prefilter list-valued source labels. Use exact cosine
    # ranking within the requested scope through the timed graph gateway instead.
    embedding = embeddings.embed_query(query)
    chunk_label = 'GraphChunk' if vector is general_vector else 'DatasheetChunk'
    rows = graph.query(f"""
        MATCH (chunk:{chunk_label})
        WHERE chunk.embedding IS NOT NULL
          AND any(label IN coalesce(chunk.labels_source, labels(chunk)) WHERE toLower(label) IN $labels)
          AND (NOT chunk:GraphChunk OR EXISTS {{ MATCH (chunk)-[:EMBEDDED_FROM]->(source)
            WHERE NOT source:StagedOntologyResource AND NOT source:RetainedOntologyIdentity AND NOT source:OntologyPublication }})
        WITH chunk, vector.similarity.cosine(chunk.embedding, $embedding) AS score
        ORDER BY score DESC LIMIT $limit
        RETURN chunk.content AS text, chunk.node_id AS node_id, chunk.labels_source AS source_labels
    """, params={"labels":wanted,"embedding":embedding,"limit":k})
    return [Document(page_content=row['text'],metadata={"node_id":row['node_id'],"source_labels":row['source_labels']}) for row in rows if row.get('text')]


def _answer(vector, chain, query, labels, k):
    if vector is None or chain is None:
        raise RuntimeError('Vector retrieval is unavailable; verify indexes and model configuration')
    if isinstance(k, bool) or not isinstance(k,int) or not 1 <= k <= 25:
        raise ValueError('k must be an integer between 1 and 25')
    docs = _retrieve_scoped(vector, query, labels, k)
    if not docs:
        return {"answer":"No matching evidence was found.","context":[],"answerable":False}
    return {"answer":chain.invoke({"input":query,"context":docs}),"context":docs,"answerable":True}


def get_data_info(query: str, labels: Optional[List[str]] = None, k: int = 5) -> Dict[str, Any]:
    _initialize_vectors()
    return _answer(datasheet_vector, data_qa_chain, query, labels, k)


def get_node_info(query: str, labels: Optional[List[str]] = None, k: int = 5) -> Dict[str, Any]:
    _initialize_vectors()
    return _answer(general_vector, general_qa_chain, query, labels, k)
