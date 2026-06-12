import os
import sys
import logging
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from core.llm import llm, embeddings, LLM_AVAILABLE, EMBEDDER_AVAILABLE
from core.graph import graph
from langchain_neo4j import Neo4jVector
from langchain_core.prompts import ChatPromptTemplate
from langchain.chains.combine_documents.stuff import create_stuff_documents_chain
from langchain.chains import create_retrieval_chain
from typing import Optional, List, Dict, Any
from langchain_core.documents import Document

logger = logging.getLogger(__name__)

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
data_retrieval_chain = None
general_qa_chain = None
general_retrieval_chain = None

if LLM_AVAILABLE and EMBEDDER_AVAILABLE:
    try:
        general_vector = Neo4jVector.from_existing_index(
            embeddings,
            graph=graph,
            index_name="graph_embedding",
            node_label="GraphChunk",
            text_node_property="content",
            embedding_node_property="embedding",
            search_type="hybrid",
            keyword_index_name="keyword_index",
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
        node_id: node.node_id
    } AS metadata
"""
        )

        datasheet_vector = Neo4jVector.from_existing_index(
            embeddings,
            graph=graph,
            index_name="datasheet_index",
            node_label="DatasheetChunk",
            text_node_property="content",
            embedding_node_property="embedding",
            search_type="hybrid",
            keyword_index_name="datasheetkeyword",
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
        filename: node.source,
        chunkID: node.chunk_id
    } AS metadata
"""
        )

        datasheet_retriever = datasheet_vector.as_retriever(search_kwargs={"k": 5})
        general_retriever = general_vector.as_retriever(search_kwargs={"k": 5})

        data_qa_chain = create_stuff_documents_chain(llm, data_prompt)
        data_retrieval_chain = create_retrieval_chain(datasheet_retriever, data_qa_chain)

        general_qa_chain = create_stuff_documents_chain(llm, general_prompt)
        general_retrieval_chain = create_retrieval_chain(general_retriever, general_qa_chain)

        logger.info("Vector chains initialized successfully")
    except Exception as exc:
        logger.warning("Vector chains could not be initialized: %s", exc)
else:
    logger.warning("LLM/EMBEDDER MODEL NOT AVAILABLE – vector chains disabled")



def format_graph_context(node_chunks, relationship_data):
    node_texts = [doc.page_content for doc in node_chunks]
    rel_texts = [] 
    for r in relationship_data:
        rel = r["rel"]
        src_label = rel["source"]["labels"][0]
        tgt_label = rel["target"]["labels"][0]
        rel_props = rel["properties"]
        rel_text = f"{src_label} →[:{rel['type']} {rel_props}]→ {tgt_label}"
        rel_texts.append(rel_text) 
    return "\n".join(node_texts + rel_texts)


def _require_general_chain():
    if not general_retrieval_chain or not general_qa_chain:
        raise RuntimeError(
            "Graph vector search is unavailable. Check backend logs and ensure the graph retriever and LLM are reachable."
        )


def _require_datasheet_chain():
    if not data_retrieval_chain or not data_qa_chain:
        raise RuntimeError(
            "Datasheet vector search is unavailable. Check backend logs and ensure the datasheet retriever and LLM are reachable."
        )


def _match_docs_by_labels(docs: List[Document], labels: Optional[List[str]]) -> List[Document]:
    wanted = {str(label).strip().lower() for label in (labels or []) if str(label).strip()}
    if not wanted or not docs:
        return docs

    node_ids = [
        str(doc.metadata.get("node_id")).strip()
        for doc in docs
        if getattr(doc, "metadata", None) and doc.metadata.get("node_id") not in (None, "")
    ]
    if not node_ids:
        return docs

    try:
        rows = graph.query(
            """
            UNWIND $node_ids AS node_id
            MATCH (n)
            WHERE toString(n.node_id) = node_id
            RETURN toString(n.node_id) AS node_id, labels(n) AS labels
            """,
            params={"node_ids": node_ids},
        )
    except Exception as exc:
        logger.warning("Label lookup for GraphRAG docs failed: %s", exc)
        return docs

    labels_by_node_id = {
        str(row.get("node_id")): {str(label).lower() for label in (row.get("labels") or [])}
        for row in rows
    }

    filtered = []
    for doc in docs:
        node_id = str(doc.metadata.get("node_id")).strip() if getattr(doc, "metadata", None) else ""
        if not node_id:
            continue
        if labels_by_node_id.get(node_id, set()) & wanted:
            filtered.append(doc)
    return filtered



def deep_vector_search(input: str):
    _require_general_chain()
    # Step 1: Retrieve node chunks 
    node_results = general_retrieval_chain.invoke({"input": input})
    node_chunks = node_results["context"] 
    node_ids = [doc.metadata["node_id"] for doc in node_chunks if "node_id" in doc.metadata]

    # Step 2: Get related relationships

    rel_query = """

    WITH $node_ids AS ids

    UNWIND ids AS nid

    MATCH (a)-[r]-(b)

    WHERE id(a) = nid OR id(b) = nid

    AND a:GraphChunk AND b:GraphChunk

    RETURN {

    type: type(r),

    properties: properties(r),

    source: {id: id(a), labels: labels(a), properties: properties(a)},

    target: {id: id(b), labels: labels(b), properties: properties(b)}

    } AS rel

    """

    relationship_data = graph.query(rel_query, params={"node_ids": node_ids})



    # Step 3: Format context and call LLM

    context = format_graph_context(node_chunks, relationship_data)
    docs = [Document(page_content=context)]

    return general_qa_chain.invoke({"input": input, "context": docs})

def get_data_info(query: str, labels: Optional[List[str]] = None, k: int = 5) -> Dict[str, Any]:
    """
    Search for any node in the graph using vector similarity and return relevant information.
    
    Args:
        query: The search query
        labels: Optional list of node labels to filter by (if None, searches all nodes)
        k: Number of results to return
        
    Returns:
        Dict containing the response with source documents
    """
    _require_datasheet_chain()
    safe_k = max(1, min(int(k or 5), 25))
    retriever = datasheet_vector.as_retriever(search_kwargs={"k": safe_k}) if datasheet_vector else None
    if retriever is None:
        result = data_retrieval_chain.invoke({"input": query})
    else:
        docs = retriever.invoke(query)
        if labels:
            docs = _match_docs_by_labels(docs, labels)
        answer = data_qa_chain.invoke({"input": query, "context": docs})
        result = {"answer": answer, "context": docs}
    return result



def get_node_info(query: str, labels: Optional[List[str]] = None, k: int = 5) -> Dict[str, Any]:
    """
    Search for any node in the graph using vector similarity and return relevant information.
    
    Args:
        query: The search query
        labels: Optional list of node labels to filter by (if None, searches all nodes)
        k: Number of results to return
        
    Returns:
        Dict containing the response with source documents
    """
    _require_general_chain()
    safe_k = max(1, min(int(k or 5), 25))
    retriever = general_vector.as_retriever(search_kwargs={"k": safe_k}) if general_vector else None
    if retriever is None:
        result = general_retrieval_chain.invoke({"input": query})
    else:
        docs = retriever.invoke(query)
        if labels:
            docs = _match_docs_by_labels(docs, labels)
        answer = general_qa_chain.invoke({"input": query, "context": docs})
        result = {"answer": answer, "context": docs}
    return result
