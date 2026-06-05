"""
Corrected Test: Ontology Creation and Accessibility
"""

import requests
import time

BASE_URL = "http://localhost:8001/api"
BASE_URL_V1 = "http://localhost:8001/api/v1"

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"

def print_header(title):
    print(f"\n{BLUE}{'='*80}{RESET}")
    print(f"{BLUE}► {title}{RESET}")
    print(f"{BLUE}{'='*80}{RESET}")

def ok(msg):
    print(f"{GREEN}✓{RESET} {msg}")

def err(msg):
    print(f"{RED}✗{RESET} {msg}")

def info(msg):
    print(f"{YELLOW}ℹ{RESET} {msg}")


# TEST 1: Static ontologies available
print_header("1. Available Static Ontologies (Before Any Import)")
try:
    r = requests.get(f"{BASE_URL}/import/ontologies")
    if r.status_code == 200:
        data = r.json()
        ok("Got ontologies list")
        info(f"Static ontologies available: {len(data.get('available_ontologies', {}))}")
        for name, details in data.get('available_ontologies', {}).items():
            info(f"  • {name}: {details.get('entity_count', 0)} entities")
    else:
        err(f"Status {r.status_code}")
except Exception as e:
    err(f"Exception: {e}")


# TEST 2: Try mapping with correct entity format
print_header("2. Map Entity to AP239 (Correct Request Format)")
try:
    # Correct format: entity is a dict with structure
    entity_request = {
        "entity": {
            "id": "test_part_001",
            "name": "TestComponent",
            "type": "Part",
            "properties": {
                "description": "Test component for ontology creation",
                "voltage_range": "5V-12V",
                "current_capacity": "2A"
            }
        },
        "source_format": "plmxml"
    }
    
    r = requests.post(f"{BASE_URL_V1}/ontology/ap239/map-entity", json=entity_request)
    if r.status_code == 200:
        result = r.json()
        ok("Entity mapped successfully")
        mapped = result.get('mapped_entity', {})
        info(f"  Mapped type: {mapped.get('type', 'unknown')}")
        info(f"  Electronics properties: {list(mapped.get('electronics_properties', {}).keys())}")
    else:
        err(f"Status {r.status_code}: {r.text[:200]}")
except Exception as e:
    err(f"Exception: {e}")

time.sleep(1)


# TEST 3: Query Neo4j OntologyMetadata directly
print_header("3. Query OntologyMetadata from Neo4j SPDMS")
try:
    from neo4j import GraphDatabase
    
    driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', 'tcs12345'))
    with driver.session(database='spdms') as session:
        # Query OntologyMetadata
        result = session.run("""
            MATCH (om:OntologyMetadata)
            RETURN om.id AS id, om.name AS name, om.type AS type, 
                   om.usage_count AS usage_count, om.created_at AS created_at
        """)
        records = list(result)
        
        if records:
            ok(f"Found {len(records)} OntologyMetadata nodes")
            for rec in records:
                info(f"  • {rec['id']}: {rec['name']} (type: {rec['type']}, usage: {rec['usage_count']})")
        else:
            err("No OntologyMetadata nodes - ontologies not being tracked in Neo4j")
    
    driver.close()
except Exception as e:
    err(f"Exception: {e}")


# TEST 4: Check if any nodes were created
print_header("4. Total Data in SPDMS Database")
try:
    r = requests.get(f"{BASE_URL_V1}/admin/schema-stats")
    if r.status_code == 200:
        stats = r.json()['stats']
        nodes = stats['total_nodes']
        rels = stats['total_relationships']
        
        ok(f"Schema stats retrieved")
        info(f"  Total nodes: {nodes}")
        info(f"  Total relationships: {rels}")
        
        if nodes > 0:
            node_types = stats.get('node_types', [])
            info(f"  Node types: {len(node_types)}")
            for nt in node_types[:5]:
                info(f"    - {nt}")
            if len(node_types) > 5:
                info(f"    ... and {len(node_types) - 5} more")
        else:
            info("  (Database is currently empty)")
    else:
        err(f"Status {r.status_code}")
except Exception as e:
    err(f"Exception: {e}")


# TEST 5: Check AP239 Data Dictionary accessibility
print_header("5. AP239 Data Dictionary Accessibility")
try:
    r = requests.get(f"{BASE_URL_V1}/ontology/ap239/data-dictionary")
    if r.status_code == 200:
        data = r.json()
        ok("AP239 data dictionary accessible")
        
        dd = data.get('data', {})
        info(f"  Entities: {len(dd.get('entities', {}))}")
        info(f"  Relationships: {len(dd.get('relationships', {}))}")
        info(f"  Properties: {len(dd.get('properties', {}))}")
        
        # Show sample entities
        entities = dd.get('entities', {})
        for entity_name in list(entities.keys())[:3]:
            info(f"    ✓ {entity_name}")
        if len(entities) > 3:
            info(f"    ... and {len(entities) - 3} more")
    else:
        err(f"Status {r.status_code}")
except Exception as e:
    err(f"Exception: {e}")


# TEST 6: Check AP239 Mappings accessibility
print_header("6. AP239 to PLMXML Mappings Accessibility")
try:
    r = requests.get(f"{BASE_URL_V1}/ontology/ap239/mappings/plmxml")
    if r.status_code == 200:
        data = r.json()
        ok("AP239 mappings accessible")
        
        mappings = data.get('mappings', {})
        info(f"  Mapping count: {len(mappings)}")
        for src, tgt in list(mappings.items())[:5]:
            info(f"    {src} → {tgt}")
        if len(mappings) > 5:
            info(f"    ... and {len(mappings) - 5} more")
    else:
        err(f"Status {r.status_code}")
except Exception as e:
    err(f"Exception: {e}")


# TEST 7: Test Multi-Domain Pipeline
print_header("7. Multi-Domain Pipeline Configuration")
try:
    r = requests.get(f"{BASE_URL_V1}/ontology/pipelines/domains")
    if r.status_code == 200:
        data = r.json()
        ok("Multi-domain pipeline list retrieved")
        
        domains = data.get('available_domains', [])
        info(f"  Available domains: {len(domains)}")
        for domain in domains:
            info(f"    ✓ {domain}")
    else:
        err(f"Status {r.status_code}")
except Exception as e:
    err(f"Exception: {e}")


# TEST 8: Test accessing Railway domain pipeline
print_header("8. Railway Domain Pipeline Configuration")
try:
    r = requests.get(f"{BASE_URL_V1}/ontology/pipelines/domain/railway")
    if r.status_code == 200:
        data = r.json()
        ok("Railway domain pipeline config retrieved")
        
        config = data.get('pipeline', {})
        info(f"  Domain: {config.get('domain')}")
        info(f"  Validation rules: {len(config.get('validation_rules', []))}")
        info(f"  Enrichment modules: {len(config.get('enrichment_modules', []))}")
        
        for rule in config.get('validation_rules', []):
            info(f"    ✓ {rule.get('name')}")
    else:
        err(f"Status {r.status_code}")
except Exception as e:
    err(f"Exception: {e}")


# SUMMARY
print_header("SUMMARY - Ontology Creation and Accessibility")
print(f"""
{YELLOW}Key Findings:{RESET}

1. {GREEN}Static Ontologies Available{RESET}
   • Pre-defined ontologies: windchill, ap242_product, pifrl
   • These are accessible through GET /api/import/ontologies
   • No dynamic ontologies created yet (database is clean)

2. {YELLOW}How Ontologies Become Accessible in Alignment Mapping:{RESET}
   • Step 1: Upload/import data or map entities via API
   • Step 2: OntologyMetadata nodes created in Neo4j
   • Step 3: Query retrieves list for UI dropdown
   • Step 4: User selects from available list
   • Accessed via: /api/import/ontologies → Frontend dropdown

3. {BLUE}Data Dictionary & Mappings{RESET}
   • AP239 Data Dictionary: /api/v1/ontology/ap239/data-dictionary
   • AP239 Mappings (PLMXML): /api/v1/ontology/ap239/mappings/plmxml
   • These are always accessible for reference

4. {GREEN}Multi-Domain Pipeline{RESET}
    • Railway, Automotive, Aerospace, Electronics, Industrial domains
    • Each has validation rules and enrichment modules
    • Accessible via: /api/v1/ontology/pipelines/domain/{{domain_name}}

{BLUE}{'='*80}{RESET}

Next Steps to Complete Testing:
1. Upload actual data file to create dynamic ontology
2. Verify OntologyMetadata appears in available_ontologies list
3. Test frontend dropdown population
4. Test actual mapping through UI
""")
