# Utility: Delete all ElectronicAssembly and ComponentInstance nodes from Neo4j
from neo4j import GraphDatabase

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "tcs12345"
NEO4J_DB = "spdms"

def delete_test_nodes():
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    with driver.session(database=NEO4J_DB) as session:
        session.run("MATCH (n) WHERE n:ElectronicAssembly OR n:ComponentInstance DETACH DELETE n")
    driver.close()
    print("Deleted all ElectronicAssembly and ComponentInstance nodes.")

if __name__ == "__main__":
    delete_test_nodes()
