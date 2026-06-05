# Utility: Clean all nodes and relationships from Neo4j (SPDMS DB)
import os
from neo4j import GraphDatabase

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "neo4j")
NEO4J_DB = "spdms"

def clean_schema():
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    with driver.session(database=NEO4J_DB) as session:
        session.run("MATCH (n) DETACH DELETE n")
    driver.close()
    print("All nodes and relationships deleted from Neo4j (SPDMS DB).")

if __name__ == "__main__":
    clean_schema()
