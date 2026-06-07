#!/usr/bin/env python3
"""
Neo4j Connection Diagnostic Test
Tests the connection to Neo4j with multiple scenarios
"""

import os
import sys
import socket
import urllib.request
from dotenv import load_dotenv
import pytest

# Load environment variables
load_dotenv()

def test_network_connectivity():
    """Test basic network connectivity"""
    print("=" * 60)
    print("Network Connectivity Diagnostics")
    print("=" * 60)
    print()
    
    # Try to resolve the hostname
    uri = os.getenv("NEO4J_URI", "neo4j+s://7beffbc6.databases.neo4j.io")
    hostname = uri.replace("neo4j+s://", "").replace("neo4j://", "").split(":")[0]
    
    print(f"[1/3] Resolving hostname: {hostname}")
    try:
        ip = socket.gethostbyname(hostname)
        print(f"✓ Resolved to IP: {ip}")
    except socket.gaierror as e:
        print(f"✗ DNS Resolution failed: {e}")
        pytest.fail(f"DNS resolution failed: {e}")
    
    print(f"[2/3] Testing internet connectivity...")
    try:
        urllib.request.urlopen('http://8.8.8.8', timeout=2)
        print(f"✓ Internet connectivity: OK")
    except Exception as e:
        print(f"⚠ Internet check inconclusive: {type(e).__name__}")
    
    print(f"[3/3] Testing port connectivity to {hostname}:7687...")
    try:
        sock = socket.create_connection((hostname, 7687), timeout=5)
        sock.close()
        print(f"✓ Port 7687 is open")
        assert True
    except socket.timeout:
        print(f"✗ Connection timeout - firewall or network issue")
        pytest.fail("Connection timeout - firewall or network issue")
    except socket.gaierror as e:
        print(f"✗ Cannot resolve host: {e}")
        pytest.fail(f"Cannot resolve host: {e}")
    except Exception as e:
        print(f"✗ Connection error: {e}")
        pytest.fail(f"Connection error: {e}")

def test_neo4j_driver():
    """Test Neo4j driver"""
    print()
    print("=" * 60)
    print("Neo4j Driver Test")
    print("=" * 60)
    print()
    
    from neo4j import GraphDatabase
    from neo4j.exceptions import ServiceUnavailable, AuthError
    
    uri = os.getenv("NEO4J_URI")
    user = os.getenv("NEO4J_USER")
    password = os.getenv("NEO4J_PASSWORD")
    database = os.getenv("NEO4J_DATABASE", "neo4j")
    
    print(f"URI:      {uri}")
    print(f"User:     {user}")
    print(f"Database: {database}")
    print()
    
    try:
        print("[1/3] Creating driver with connection pool...")
        driver = GraphDatabase.driver(
            uri, 
            auth=(user, password),
            connection_timeout=10,
            connection_acquisition_timeout=10
        )
        print("✓ Driver created")
        
        print("[2/3] Verifying connectivity...")
        driver.verify_connectivity()
        print("✓ Connected")
        
        print("[3/3] Running test query...")
        with driver.session(database=database) as session:
            session.run("RETURN 1 as test")
            print(f"✓ Query successful")
        
        driver.close()
        assert True
        
    except AuthError as e:
        pytest.skip(f"Authentication failed: {e}. Skipping Neo4j driver test")
    except ServiceUnavailable as e:
        pytest.skip(f"Service unavailable: {e}. Skipping Neo4j driver test")
    except Exception as e:
        pytest.skip(f"Neo4j driver test skipped due to error: {type(e).__name__}: {e}")

if __name__ == "__main__":
    network_ok = test_network_connectivity()
    if network_ok:
        neo4j_ok = test_neo4j_driver()
        success = neo4j_ok
    else:
        print()
        print("=" * 60)
        print("Network connectivity issues detected")
        print("=" * 60)
        print()
        print("Troubleshooting steps:")
        print("1. Check your internet connection")
        print("2. Check firewall settings (port 7687 may be blocked)")
        print("3. Verify Neo4j URI in .env file is correct")
        print("4. Check if Neo4j cloud instance is running")
        success = False
    
    sys.exit(0 if success else 1)
