from neo4j import GraphDatabase

driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', 'tcs12345'))

try:
    with driver.session(database='spdms') as session:
        # Get total nodes and types
        result = session.run('MATCH (n) RETURN count(n) as total, collect(distinct labels(n)) as types LIMIT 1')
        record = result.single()
        if record:
            print(f'Total nodes: {record["total"]}')
            print(f'Node types: {record["types"]}')
        else:
            print('No nodes found')
        
        # Get sample nodes
        result = session.run('MATCH (n) RETURN labels(n) as labels, n LIMIT 20')
        for record in result:
            print(f'  - {record["labels"]}: {dict(record["n"])}')
        
        # Get relationships
        result = session.run('MATCH ()-[r]-() RETURN count(r) as total, collect(distinct type(r)) as types LIMIT 1')
        record = result.single()
        if record:
            print(f'Total relationships: {record["total"]}')
            print(f'Rel types: {record["types"]}')
finally:
    driver.close()
