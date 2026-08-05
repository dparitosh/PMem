import os
import sys
import logging
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from core.llm import llm, LLM_AVAILABLE
from core.graph import graph
try:
    from backend.core.cypher_safety import assert_read_only_cypher
    from backend.core.graph import query_with_timeout
except Exception:
    from core.cypher_safety import assert_read_only_cypher
    from core.graph import query_with_timeout
from langchain_neo4j import GraphCypherQAChain, Neo4jGraph
from langchain.prompts.prompt import PromptTemplate
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

schema = graph.get_schema
# print(schema)

CYPHER_GENERATION_TEMPLATE = """
You are a Cypher expert working with a Neo4j knowledge graph.
Given the graph schema and a user's question,  your task is to generate accurate Cypher queries strictly based on the provided schema.

Important Instructions:
1. Use only the labels, relationship types, and properties explicitly mentioned in the schema.
2. Do not invent or assume any labels, properties, or relationships that are not present in the schema.
3. Your Cypher query must only return what the user's question asks for, using correct syntax.
4. Do not include any explanations, comments, or edits to the schema.
5. Ensure property names and label names are case-sensitive and match exactly what is in the schema.
6. Do not truncate the number of results.
7. Do not use any limit until explicitly asked.

Examples:

1. User Query: "Give me details about XXXXX process."
   Cypher generated: match (n:Process) where n.name="XXXXX" return n

2. User Query: "Search for CAD assembly XXXXX"
   Cypher generated: match (n:Assembly)-[r]-(m) where n.FileName="XXXXX" return n,r,m

3. User Query: "List me the parent of XXXXX"
   Cypher generated: MATCH (n)-[r:HAS_PARENT]->(m) where n.name="XXXXX" RETURN n, r, m

4. User Query[IMPORTANT]: "Fetch traceability graph from windchill as per sysML version 1 upto component level"
   Cypher generated: match (n:UMLModel)-[r*4]-(m) return n,r,m

5. User Query: "List down the requirements associated with the Induction motor"
   Cypher generated: match (n:Requirement) return n.name as `Name/Description`

6. User Query: "Give me details of mBoM_HV Induction motor node"
   Cypher generated: MATCH (n:Product)-[r:HAS_CHILD*]-(m) where n.name = "mBoM_HV Induction Motor" return n.name as Parent, m.name as Child

7. User Query: "List out the assoiciated processes of Plant BoP - Induction Motor Assembly"
   Generated cypher: MATCH (n:Process)-[r:HAS_CHILD*]-(m:Process) where n.name = "Plant BoP - Induction Motor Assembly" return n.name as Parent, m.name as Child

Given a user question, generate only one Cypher query. Do not include explanations or ask follow-up questions.
DO NOT limit or truncate the results. Be consistent and accurate.
**If the User Question is present in the examples, USE the EXACT cypher as mentioned in the EXAMPLES.**
DO NOT create Cypher query on your own. Always refer to examples & schema for creating new Cypher queries that are not given in Examples.
Always stick to the examples.


Schema:
{schema}

User Question:
{question}
"""

cypher_prompt = PromptTemplate.from_template(CYPHER_GENERATION_TEMPLATE)

cypher_qa = None


# ✅ FIXED: GraphStore Adapter Wrapper
# ========================================
# Problem: GraphCypherQAChain.from_llm() expects langchain_neo4j.GraphStore interface
# but receives Neo4jGraph (GraphProxy wrapper from langchain_neo4j)
#
# Solution: Create adapter that wraps Neo4jGraph to satisfy GraphStore type checking
# while preserving all underlying functionality.
class Neo4jGraphStoreAdapter:
    """
    Adapter to make Neo4jGraph compatible with GraphCypherQAChain's GraphStore interface.
    
    GraphCypherQAChain.from_llm() expects:
    - Type annotation checking for GraphStore (pydantic validation)
    - query(cypher_query: str) -> List[Dict[str, Any]]
    - get_schema() -> str
    
    This adapter wraps Neo4jGraph to provide these interfaces.
    """
    
    def __init__(self, neo4j_graph: Neo4jGraph):
        """
        Initialize adapter.
        
        Args:
            neo4j_graph: Neo4jGraph instance from langchain_neo4j
        """
        self._graph = neo4j_graph
        self._schema = None
    
    def query(self, query: str) -> List[Dict[str, Any]]:
        """
        Execute a Cypher query.
        
        Args:
            query: Cypher query string
            
        Returns:
            List of result records as dictionaries
        """
        try:
            result = query_with_timeout(assert_read_only_cypher(query))
            logger.debug(f"Cypher query executed: {query[:100]}... | Results: {len(result) if isinstance(result, list) else 'dict'}")
            return result
        except Exception as exc:
            logger.error(f"Cypher query failed: {query[:100]}... | Error: {exc}")
            raise
    
    def get_schema(self) -> str:
        """
        Get the Neo4j graph schema.
        
        Returns:
            Schema as string
        """
        if self._schema is None:
            self._schema = self._graph.get_schema()
        return self._schema
    
    def __getattr__(self, name: str):
        """
        Delegate unknown attributes to underlying Neo4jGraph.
        
        This allows the adapter to transparently wrap Neo4jGraph while
        preserving any additional methods or properties.
        """
        return getattr(self._graph, name)
    
    def __repr__(self) -> str:
        return f"Neo4jGraphStoreAdapter({self._graph!r})"


if LLM_AVAILABLE:
    try:
        # ✅ FIXED: Wrap graph in adapter to satisfy type checking
        graph_adapter = Neo4jGraphStoreAdapter(graph)
        
        cypher_qa = GraphCypherQAChain.from_llm(
            llm=llm,
            graph=graph_adapter,  # Use adapter instead of raw graph
            verbose=True,
            cypher_prompt=cypher_prompt,
            allow_dangerous_requests=True,
            return_direct=True,
            return_intermediate_steps=True,
        )
        logger.info("✅ Cypher QA chain initialized successfully (with GraphStore adapter)")
    except Exception as exc:
        # Fallback: log detailed error for debugging
        logger.warning(
            "❌ Cypher QA chain could not be initialized with adapter: %s\n"
            "Falling back to direct Cypher queries (no LLM-based generation)\n"
            "Details: %s",
            type(exc).__name__,
            exc
        )
        cypher_qa = None
else:
    logger.warning("LLM/EMBEDDER MODEL NOT AVAILABLE – Cypher QA chain disabled")


# ============================================
# FALLBACK: Direct Cypher Query Function
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
        GraphCypherQAChain or None
    """
    return cypher_qa


def cypher_qa_available() -> bool:
    """
    Check if Cypher QA chain is available.
    
    Returns:
        True if cypher_qa chain initialized successfully
    """
    return cypher_qa is not None
