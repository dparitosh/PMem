from neo4j import GraphDatabase
d = GraphDatabase.driver("neo4j://127.0.0.1:7687", auth=("neo4j", "tcs12345"))
with d.session(database="spdm") as s:
    s.run("MATCH (n) DETACH DELETE n")
    c = s.run("MATCH (n) RETURN count(n) AS c").single()["c"]
    print("Remaining nodes:", c)
d.close()
