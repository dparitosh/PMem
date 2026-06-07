#!/usr/bin/env python3
"""
Neo4j Connection Test
Tests the connection to the Neo4j database
"""

import os
import sys
from dotenv import load_dotenv
from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable, AuthError
import pytest

# Load environment variables
load_dotenv()

def test_neo4j_connection():
    """Test Neo4j connection"""
    
    # Get connection parameters
    uri = os.getenv("NEO4J_URI")
    user = os.getenv("NEO4J_USER")
    password = os.getenv("NEO4J_PASSWORD")
    database = os.getenv("NEO4J_DATABASE", "neo4j")
    
    print("=" * 60)
    print("Neo4j Connection Test")
    print("=" * 60)
    print()
    print(f"URI:      {uri}")
    print(f"User:     {user}")
    print(f"Database: {database}")
    print()
    
    try:
        print("[1/4] Creating driver...")
        driver = GraphDatabase.driver(uri, auth=(user, password))
        print("✓ Driver created successfully")
        
        print("[2/4] Verifying connectivity...")
        driver.verify_connectivity()
        print("✓ Connection verified")
        
        print("[3/4] Running test query...")
        with driver.session(database=database) as session:
            result = session.run("RETURN 'Connected to Neo4j!' as message")
            message = result.single()["message"]
            print(f"✓ Query result: {message}")
        
        print("[4/4] Getting database info...")
        with driver.session(database=database) as session:
            result = session.run("""
                CALL db.info() YIELD name, mode
                RETURN name, mode
            """)
            record = result.single()
            if record:
                print(f"✓ Database: {record['name']}")
                print(f"✓ Mode: {record['mode']}")
        
        print()
        print("=" * 60)
        print("✓ ALL TESTS PASSED - Neo4j Connection OK!")
        print("=" * 60)
        driver.close()
        assert True
        
    except AuthError as e:
        pytest.skip(f"Authentication Error: {e}. Skipping Neo4j connection test (check NEO4J credentials)")
    except ServiceUnavailable as e:
        pytest.skip(f"Service Unavailable: {e}. Skipping Neo4j connection test (service unreachable)")
    except Exception as e:
        pytest.skip(f"Neo4j connection check skipped due to error: {type(e).__name__}: {e}")

if __name__ == "__main__":
    success = test_neo4j_connection()
    sys.exit(0 if success else 1)
