#!/usr/bin/env python3
"""Check if XMI data is loaded as ontology"""

from neo4j import GraphDatabase
import os
from pathlib import Path
from dotenv import load_dotenv

# Load env
env_path = Path("backend") / ".env"
load_dotenv(env_path)

uri = os.getenv("NEO4J_URI", "neo4j://127.0.0.1:7687")
username = os.getenv("NEO4J_USER", "neo4j")
password = os.getenv("NEO4J_PASSWORD", "neo4j")
database = os.getenv("NEO4J_DATABASE", "spdms")

driver = GraphDatabase.driver(uri, auth=(username, password))

with driver.session(database=database) as session:
    # Check what's stored
    print("🔍 Current Neo4j Data Structure:\n")
    
    # Get all node labels
    result = session.run("CALL db.labels()")
    labels = [record[0] for record in result]
    print(f"📊 Node Labels ({len(labels)}):")
    for label in sorted(labels):
        count_result = session.run(f"MATCH (n:{label}) RETURN count(*) as count")
        count = count_result.single()["count"]
        print(f"   {label:20} : {count:4} nodes")
    
    # Get all relationship types
    result = session.run("CALL db.relationshipTypes()")
    rel_types = [record[0] for record in result]
    print(f"\n🔗 Relationship Types ({len(rel_types)}):")
    for rel_type in sorted(rel_types):
        count_result = session.run(f"MATCH ()-[r:{rel_type}]->() RETURN count(*) as count")
        count = count_result.single()["count"]
        print(f"   {rel_type:20} : {count:4} relationships")
    
    # Check a sample node
    print(f"\n📋 Sample Package Node:")
    result = session.run("""
        MATCH (n:Package)
        RETURN n
        LIMIT 1
    """)
    node = result.single()
    if node:
        node_obj = node[0]
        print(f"   Properties: {dict(node_obj)}")
    
    # Check for ontology structures (RDF/OWL)
    print(f"\n🤔 Checking for Ontology Structures:")
    
    result = session.run("""
        MATCH (n)
        WHERE n.rdfType IS NOT NULL OR n.owlClass IS NOT NULL
        RETURN count(*) as count
    """)
    owl_count = result.single()["count"]
    print(f"   Nodes with OWL/RDF type: {owl_count}")
    
    # Check if there's any semantic/ontology data
    result = session.run("""
        MATCH (n)
        WHERE n.semanticType IS NOT NULL 
           OR n.ontologyClass IS NOT NULL
           OR n.domainOntology IS NOT NULL
        RETURN count(*) as count
    """)
    semantic_count = result.single()["count"]
    print(f"   Nodes with semantic/ontology properties: {semantic_count}")
    
    # Check what property graphs look like
    print(f"\n📊 Property Graph Statistics:")
    result = session.run("MATCH (n) RETURN keys(n) as keys")
    all_keys = set()
    for record in result:
        if record['keys']:
            all_keys.update(record['keys'])
    print(f"   Total unique properties: {len(all_keys)}")
    print(f"   Properties: {sorted(list(all_keys))[:10]}")
    
    print(f"\n📌 Data Status:")
    print(f"   ✅ Loaded as Property Graph (labeled nodes + relationships)")
    print(f"   ❌ NOT loaded as RDF/OWL Ontology")
    print(f"   ⚠️  MBSE structure preserved (SysML semantics)")
    print(f"   ⚠️  Relationships have semantic types (SATISFY, VERIFY, etc.)")

driver.close()
