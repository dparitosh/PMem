#!/usr/bin/env python3
"""Clear Neo4j database for fresh testing"""

from neo4j import GraphDatabase
import os
from pathlib import Path
from dotenv import load_dotenv

# Load env file from backend
env_path = Path(__file__).parent / "backend" / ".env"
load_dotenv(env_path)

# Connect to Neo4j
uri = os.getenv("NEO4J_URI", "neo4j://127.0.0.1:7687")
username = os.getenv("NEO4J_USER", "neo4j")
password = os.getenv("NEO4J_PASSWORD", "neo4j")
database = os.getenv("NEO4J_DATABASE", "spdms")

try:
    driver = GraphDatabase.driver(uri, auth=(username, password))
    
    with driver.session(database=database) as session:
        # Clear all nodes and relationships
        result = session.run("MATCH (n) DETACH DELETE n RETURN count(*) as deleted")
        count = result.single()["deleted"]
        print(f"✅ Neo4j cleared: {count} nodes deleted from database '{database}'")
        
        # Verify it's empty
        result = session.run("MATCH (n) RETURN count(*) as count")
        remaining = result.single()["count"]
        print(f"✅ Verification: {remaining} nodes remaining (should be 0)")
    
    driver.close()
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
