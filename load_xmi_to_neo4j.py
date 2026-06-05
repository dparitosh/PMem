#!/usr/bin/env python3
"""Load XMI data into Neo4j and verify"""

from pathlib import Path
from backend.backend.Services.xmi_parser import XMIParser
from neo4j import GraphDatabase
import os
from dotenv import load_dotenv
import json

# Load env
env_path = Path("backend") / ".env"
load_dotenv(env_path)

# Get credentials
uri = os.getenv("NEO4J_URI", "neo4j://127.0.0.1:7687")
username = os.getenv("NEO4J_USER", "neo4j")
password = os.getenv("NEO4J_PASSWORD", "neo4j")
database = os.getenv("NEO4J_DATABASE", "spdms")

# Parse XMI
print("📄 Parsing XMI file...")
xmi_file = Path(r"c:\Users\895428\Depo\SPLM_Folder\XMI\SugarPlantMBSE.xmi")
parser = XMIParser()
result = parser.parse(xmi_file)

print(f"✅ Parsed: {len(result['nodes'])} nodes, {len(result['relationships'])} relationships")

# Group nodes by type
node_types = {}
for node in result['nodes']:
    label = node.get('label', 'Unknown')
    node_types[label] = node_types.get(label, 0) + 1

print(f"\n📊 Nodes by type:")
for ntype, count in sorted(node_types.items(), key=lambda x: x[1], reverse=True):
    print(f"   {ntype}: {count}")

# Connect to Neo4j and load data
print(f"\n🔗 Connecting to Neo4j at {uri} (database: {database})...")
driver = GraphDatabase.driver(uri, auth=(username, password))

try:
    with driver.session(database=database) as session:
        # Create nodes
        nodes_created = 0
        for node in result['nodes']:
            label = node.get('label', 'Element')
            props = node.get('properties', {})
            
            # Create property dict with escaped keys
            prop_dict = {}
            for k, v in props.items():
                if v is not None:
                    # Replace problematic characters in keys
                    safe_key = k.replace('-', '_').replace(' ', '_').replace('.', '_')
                    prop_dict[safe_key] = v
            
            # Build the query
            prop_list = ', '.join(f'{k}: ${k}' for k in prop_dict.keys())
            if prop_list:
                query = f"CREATE (n:{label} {{{prop_list}}})"
                session.run(query, **prop_dict)
            else:
                session.run(f"CREATE (n:{label})")
            
            nodes_created += 1
        
        print(f"✅ Created {nodes_created} nodes")
        
        # Create relationships
        rels_created = 0
        for rel in result['relationships']:
            from_id = rel.get('from_props', {}).get('id')
            to_id = rel.get('to_props', {}).get('id')
            rel_type = rel.get('type', 'RELATED')
            
            if from_id and to_id:
                query = f"""
                MATCH (from {{id: $from_id}})
                MATCH (to {{id: $to_id}})
                CREATE (from)-[r:{rel_type}]->(to)
                """
                try:
                    session.run(query, from_id=from_id, to_id=to_id)
                    rels_created += 1
                except Exception as e:
                    # Skip if nodes don't exist (property refs, etc.)
                    pass
        
        print(f"✅ Created {rels_created} relationships")
        
        # Verify data
        result = session.run("MATCH (n) RETURN count(*) as count")
        total_nodes = result.single()["count"]
        
        result = session.run("MATCH ()-[r]->() RETURN count(*) as count")
        total_rels = result.single()["count"]
        
        print(f"\n✅ Neo4j verification:")
        print(f"   Total nodes: {total_nodes}")
        print(f"   Total relationships: {total_rels}")
        
        # Show sample nodes by type
        print(f"\n📋 Sample nodes:")
        result = session.run("""
            MATCH (n)
            RETURN labels(n)[0] as type, n.name as name, count(*) as count
            ORDER BY count DESC
            LIMIT 10
        """)
        for record in result:
            print(f"   {record['type']:20} ({record['count']:3}): {record['name']}")
        
finally:
    driver.close()

print("\n✅ XMI data successfully loaded into Neo4j!")
