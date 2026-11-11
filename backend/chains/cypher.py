import logging
import re
from backend.core.llm import llm, LLM_AVAILABLE
from backend.core.graph import graph, query_with_timeout
from langchain.prompts.prompt import PromptTemplate
from typing import Optional, List, Dict, Any

from backend.core.cypher_safety import assert_read_only_cypher
from backend.core.db_config import get_config

logger = logging.getLogger(__name__)

CYPHER_GENERATION_TEMPLATE = """
You are a Cypher expert working with a Neo4j knowledge graph for a Digital Engineering Product Ontology (DEPO).

Use the supplied schema as the only authority for labels, relationship types and
properties. Domain examples, prefixes and source-system names are not universal.

Instructions:
1. Use only labels, relationships and properties present in the supplied schema.
2. Do not assume a particular ontology prefix, source system or engineering model.
3. Apply an ontology or import scope only when supplied explicitly by the user and
   supported by the schema. Do not infer scope from a similar term name.
4. Return only the requested evidence. If the schema cannot answer the question,
   explain the missing evidence rather than inventing a query or an entity.
5. Generate a read-only query. Never generate mutations, procedures with side
   effects, schema changes, or external network/file operations.
6. Property names are case-sensitive. Use bounded results for broad questions.

Schema:
{schema}

User Question:
{question}
"""

cypher_prompt = PromptTemplate.from_template(CYPHER_GENERATION_TEMPLATE)

cypher_qa = None


class ReadOnlyGraphAdapter:
    """Delegate schema access while enforcing read-only, timed query execution."""

    def __init__(self, wrapped_graph):
        self._graph = wrapped_graph

    def query(self, query: str, params: Optional[dict] = None):
        return query_with_timeout(assert_read_only_cypher(query), params=params)

    def __getattr__(self, name):
        return getattr(self._graph, name)


readonly_graph = ReadOnlyGraphAdapter(graph)


class SafeCypherQA:
    """Generate one Cypher statement and execute it through the read-only gateway."""

    @staticmethod
    def _extract_query(response: Any) -> str:
        text = getattr(response, "content", response)
        if isinstance(text, list):
            text = "".join(
                str(item.get("text", "") if isinstance(item, dict) else item)
                for item in text
            )
        text = str(text or "").strip()
        fenced = re.search(r"```(?:cypher)?\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL)
        if fenced:
            text = fenced.group(1).strip()
        text = re.sub(r"^\s*(?:cypher(?:\s+query)?\s*:)\s*", "", text, flags=re.IGNORECASE)
        return assert_read_only_cypher(text)

    def invoke(self, payload: Any) -> Dict[str, Any]:
        question = payload.get("query") or payload.get("question") or payload.get("input") if isinstance(payload, dict) else payload
        prompt = cypher_prompt.format(schema=graph.get_schema, question=str(question or ""))
        generated = llm.invoke(prompt)
        query = self._extract_query(generated)
        rows = readonly_graph.query(query)
        return {"result": rows, "intermediate_steps": [{"query": query}]}

    def __call__(self, question: str) -> Dict[str, Any]:
        return self.invoke({"query": question})


# ============================================
# Cypher QA Chain Initialization (With Fallback)
# ============================================
if LLM_AVAILABLE:
    try:
        cypher_qa = SafeCypherQA()
        logger.info("Cypher QA chain initialized successfully")

    except Exception as exc:
        logger.debug(
            "Cypher QA initialization unavailable: %s",
            type(exc).__name__
        )
        cypher_qa = None
else:
    logger.info("LLM not available - Cypher QA chain disabled")


# ============================================
# FALLBACK: Direct Cypher Query Functions
# ============================================
def query_cypher(query: str) -> List[Dict[str, Any]]:
    """
    Execute Cypher query directly without LLM.

    Use this as fallback if cypher_qa chain is unavailable.

    Args:
        query: Cypher query string

    Returns:
        List of result records

    Example:
        >>> results = query_cypher("MATCH (n:Product) RETURN n.name LIMIT 10")
        >>> for record in results:
        ...     print(record)
    """
    try:
        return query_with_timeout(assert_read_only_cypher(query))
    except Exception as exc:
        logger.error(f"Direct Cypher query failed: {exc}")
        raise


def get_cypher_qa():
    """
    Get the Cypher QA chain if available, otherwise None.

    Returns:
        SafeCypherQA or None
    """
    return cypher_qa


def cypher_qa_available() -> bool:
    """
    Check if Cypher QA chain is available.

    Returns:
        True if cypher_qa chain initialized successfully
    """
    return cypher_qa is not None
