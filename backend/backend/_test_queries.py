import os, json, time
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / '.env')
from langchain_neo4j import Neo4jGraph
uri = os.getenv('NEO4J_URI') or os.getenv('NEO4J_URL') or os.getenv('Neo4j_url')
user = os.getenv('NEO4J_USER') or os.getenv('NEO4J_USERNAME') or os.getenv('Neo4j_user')
pwd = os.getenv('NEO4J_PASS') or os.getenv('NEO4J_PASSWORD') or os.getenv('Neo4j_password')
db = os.getenv('NEO4J_DATABASE') or os.getenv('Neo4j_database') or 'neo4j'
g = Neo4jGraph(url=uri, username=user, password=pwd, database=db)

print('=== AP242 QUERY (all /ontology/ + step-ontology) ===')
t0 = time.time()
r1 = g.query("""
MATCH (n)-[r]-(m)
WHERE n.namespace CONTAINS '/ontology/'
   OR n.namespace CONTAINS 'step-ontology'
RETURN
  {elementId: elementId(n), labels: labels(n), properties: properties(n)} AS n,
  {elementId: elementId(r), type: type(r), properties: properties(r),
   start: elementId(startNode(r)), end: elementId(endNode(r))} AS r,
  {elementId: elementId(m), labels: labels(m), properties: properties(m)} AS m
LIMIT 500
""")
print(f"AP242: {len(r1)} rows in {time.time()-t0:.2f}s")

print()
print('=== PLMXML QUERY ===')
t0 = time.time()
r2 = g.query("""
MATCH (n)-[r]-(m)
WHERE n.namespace CONTAINS 'plmxml-ontology'
   OR m.namespace CONTAINS 'plmxml-ontology'
RETURN
  {elementId: elementId(n), labels: labels(n), properties: properties(n)} AS n,
  {elementId: elementId(r), type: type(r), properties: properties(r),
   start: elementId(startNode(r)), end: elementId(endNode(r))} AS r,
  {elementId: elementId(m), labels: labels(m), properties: properties(m)} AS m
LIMIT 500
""")
print(f"PLMXML: {len(r2)} rows in {time.time()-t0:.2f}s")

print()
print('=== STEP QUERY (node-only) ===')
t0 = time.time()
r3 = g.query("""
MATCH (n)
WHERE n.namespace CONTAINS 'step-ap242'
RETURN
  {elementId: elementId(n), labels: labels(n), properties: properties(n)} AS n,
  null AS r, null AS m
LIMIT 300
""")
print(f"STEP: {len(r3)} rows in {time.time()-t0:.2f}s")

print()
print('=== STEP PART FALLBACK (Rotor_Shaft_Machined) ===')
t0 = time.time()
# Test the part-specific fallback
pf = 'Rotor_Shaft_Machined'
r4_rel = g.query("""
MATCH (n)-[r]-(m)
WHERE (n.namespace CONTAINS $part_filter OR m.namespace CONTAINS $part_filter)
RETURN count(*) AS cnt
""", params={"part_filter": pf})
print(f"Part rels for {pf}: {r4_rel[0]['cnt']}")
r4_node = g.query("""
MATCH (n)
WHERE n.namespace CONTAINS $part_filter AND n.namespace CONTAINS 'step-ap242'
RETURN count(n) AS cnt
""", params={"part_filter": pf})
print(f"Part nodes for {pf}: {r4_node[0]['cnt']}")

