import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from core.llm import llm
from core.graph import graph
from langchain_neo4j import GraphCypherQAChain
from langchain.prompts.prompt import PromptTemplate

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
   Generated cypher: MATCH (n:Process)-[r:HAS_CHILD*]-(m) where n.name = "Plant BoP - Induction Motor Assembly" return n.name as Parent, m.name as Child

Given a user question, generate only one Cypher query. Do not include explanations or ask follow-up questions.
DO NOT limit or truncate the results. Be consistent and accurate.
ALWAYS use the SCHEMA to generate the cypher.
If the User Question is present in the examples, USE the EXACT cypher as mentioned in the EXAMPLES.
DO NOT create Cypher query on your own. Always refer to examples & schema for creating new Cypher queries that are not given in Examples.
Always stick to the examples.


Schema:
{schema}

User Question:
{question}
"""

cypher_prompt = PromptTemplate.from_template(CYPHER_GENERATION_TEMPLATE)

# print(cypher_prompt.format(schema=schema, question='I am ?'))

cypher_qa = GraphCypherQAChain.from_llm(
    llm=llm,
    graph=graph,
    verbose=True,
    cypher_prompt=cypher_prompt,
    allow_dangerous_requests=True,
    return_direct = True,
    return_intermediate_steps = True
)

# res = cypher_qa.invoke("""find similar IPs (Design Blocks) : 7up_uart""")
# query = res["intermediate_steps"][0]["query"]
# lines = query.strip().splitlines()
# if lines and lines[0].strip().lower() in {"cypher", "cypher:"}:
#     lines = lines[1:]
#     lines = "\n".join(lines).strip()

# print(f"Query: {lines}")
# print(f"Type: {type(lines)}")
# print(f"Query: {res["intermediate_steps"][0]["query"]}")
# print(res)
