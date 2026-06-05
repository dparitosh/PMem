from backend.backend.core.graph import graph

r1 = graph.query("MATCH (n) WHERE n.source_format = 'xmi' RETURN count(n) AS c")
r2 = graph.query("MATCH (n) RETURN count(n) AS c")

print("xmi_nodes", r1[0]["c"] if r1 else 0)
print("all_nodes", r2[0]["c"] if r2 else 0)
