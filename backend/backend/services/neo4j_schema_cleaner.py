r"""
Neo4j Schema Cleaner & Management Service
Cleans and manages Neo4j schema for testing and production use
"""

import logging
import os
from typing import Dict, List, Any, Tuple
from neo4j import GraphDatabase, Session
from dataclasses import dataclass
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


@dataclass
class SchemaStats:
    """Schema statistics"""
    total_nodes: int
    total_relationships: int
    node_types: List[str]
    relationship_types: List[str]
    indexes: List[str]
    constraints: List[str]


class Neo4jSchemaCleaner:
    r"""
    Neo4j Schema Cleaner for test data cleanup and schema management
    Supports:
    - Full database wipe
    - Selective node/relationship deletion
    - Index management
    - Constraint management
    - Schema statistics
    """
    
    def __init__(self, uri: str = None, username: str = None, password: str = None, database: str = None):
        """
        Initialize Neo4j connection
        
        Args:
            uri: Neo4j connection URI (default: from NEO4J_URI env or bolt://localhost:7687)
            username: Neo4j username (default: from NEO4J_USER env or neo4j)
            password: Neo4j password (default: from NEO4J_PASSWORD env or neo4j)
            database: Neo4j database name (default: from NEO4J_DATABASE env or spdms)
        """
        # Read from environment or use provided values or fallback defaults
        self.uri = uri or os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.username = username or os.getenv("NEO4J_USER", "neo4j")
        self.password = password or os.getenv("NEO4J_PASSWORD", "neo4j")
        self.database = database or os.getenv("NEO4J_DATABASE", "spdms")
        self.driver = None
        
        try:
            self.driver = GraphDatabase.driver(self.uri, auth=(self.username, self.password))
            # Test connection
            with self.driver.session(database=self.database) as session:
                result = session.run("RETURN 1")
                _ = result.single()
            logger.info("[OK] Neo4j connection established")
        except Exception as e:
            logger.error(f"[ERROR] Neo4j connection failed: {str(e)}")
    
    def get_schema_stats(self) -> SchemaStats:
        """Get current schema statistics"""
        if not self.driver:
            return SchemaStats(0, 0, [], [], [], [])
        
        try:
            with self.driver.session(database=self.database) as session:
                # Count nodes and relationships
                node_result = session.run("MATCH (n) RETURN count(n) as count")
                node_record = node_result.single()
                node_count = node_record["count"] if node_record else 0
                
                rel_result = session.run("MATCH ()-[r]-() RETURN count(r) as count")
                rel_record = rel_result.single()
                rel_count = rel_record["count"] if rel_record else 0
                
                # Get node types
                node_types_result = list(session.run(
                    "MATCH (n) RETURN distinct labels(n) as labels"
                ))
                node_types = []
                for record in node_types_result:
                    labels = record["labels"]
                    if labels:
                        node_types.extend(labels)
                node_types = list(set(node_types))
                
                # Get relationship types
                rel_types_result = list(session.run(
                    "MATCH ()-[r]-() RETURN distinct type(r) as type"
                ))
                rel_types = [record["type"] for record in rel_types_result]
                
                # Get indexes
                index_result = list(session.run(
                    "SHOW INDEXES"
                ))
                indexes = [f"{r['name']}: {r['type']}" for r in index_result]
                
                # Get constraints
                constraint_result = list(session.run(
                    "SHOW CONSTRAINTS"
                ))
                constraints = [f"{c['name']}: {c['type']}" for c in constraint_result]
                
                return SchemaStats(
                    total_nodes=node_count,
                    total_relationships=rel_count,
                    node_types=node_types,
                    relationship_types=rel_types,
                    indexes=indexes,
                    constraints=constraints
                )
        except Exception as e:
            logger.error(f"[ERROR] Failed to get schema stats: {str(e)}")
            return SchemaStats(0, 0, [], [], [], [])
    
    def delete_all_nodes_and_relationships(self) -> Tuple[bool, str]:
        """
        Delete ALL nodes and relationships from database
        WARNING: This is destructive and cannot be undone!
        """
        if not self.driver:
            return False, "No database connection"
        
        try:
            with self.driver.session(database=self.database) as session:
                # First delete relationships, then nodes
                rel_result = session.run("MATCH ()-[r]-() DELETE r RETURN count(r) as count")
                rel_record = rel_result.single()
                rel_deleted = rel_record["count"] if rel_record else 0
                
                node_result = session.run("MATCH (n) DELETE n RETURN count(n) as count")
                node_record = node_result.single()
                node_deleted = node_record["count"] if node_record else 0
                
                logger.warning(f"[WARN] Deleted {node_deleted} nodes and {rel_deleted} relationships")
                return True, f"Deleted {node_deleted} nodes, {rel_deleted} relationships"
        except Exception as e:
            logger.error(f"[ERROR] Failed to delete nodes: {str(e)}")
            return False, str(e)
    
    def delete_nodes_by_type(self, node_type: str) -> Tuple[bool, str]:
        """Delete all nodes of a specific type"""
        if not self.driver:
            return False, "No database connection"
        
        try:
            with self.driver.session(database=self.database) as session:
                result = session.run(f"MATCH (n:{node_type}) DELETE n RETURN count(n) as count")
                record = result.single()
                count = record["count"] if record else 0
                logger.info(f"[OK] Deleted {count} nodes of type {node_type}")
                return True, f"Deleted {count} {node_type} nodes"
        except Exception as e:
            logger.error(f"[ERROR] Failed to delete {node_type} nodes: {str(e)}")
            return False, str(e)
    
    def delete_relationships_by_type(self, rel_type: str) -> Tuple[bool, str]:
        """Delete all relationships of a specific type"""
        if not self.driver:
            return False, "No database connection"
        
        try:
            with self.driver.session(database=self.database) as session:
                result = session.run(f"MATCH ()-[r:{rel_type}]-() DELETE r RETURN count(r) as count")
                record = result.single()
                count = record["count"] if record else 0
                logger.info(f"[OK] Deleted {count} relationships of type {rel_type}")
                return True, f"Deleted {count} {rel_type} relationships"
        except Exception as e:
            logger.error(f"[ERROR] Failed to delete {rel_type} relationships: {str(e)}")
            return False, str(e)
    
    def create_indexes(self) -> Tuple[bool, str]:
        """Create standard indexes for AP239 ontology"""
        if not self.driver:
            return False, "No database connection"
        
        # Neo4j 5.x compatible index syntax
        indexes_to_create = [
            "CREATE INDEX idx_entity_id IF NOT EXISTS FOR (n:Entity) ON (n.id)",
            "CREATE INDEX idx_entity_type IF NOT EXISTS FOR (n:Entity) ON (n.type)",
            "CREATE INDEX idx_entity_name IF NOT EXISTS FOR (n:Entity) ON (n.name)",
        ]
        
        try:
            with self.driver.session(database=self.database) as session:
                for index_query in indexes_to_create:
                    try:
                        session.run(index_query)
                    except Exception as idx_err:
                        # Log but don't fail - indexes may not be necessary
                        logger.warning(f"[WARN] Could not create index: {str(idx_err)[:100]}")
                        continue
            logger.info("[OK] Index creation completed")
            return True, "Indexes created successfully"
        except Exception as e:
            logger.error(f"[ERROR] Failed to create indexes: {str(e)}")
            return False, str(e)
    
    def drop_all_indexes(self) -> Tuple[bool, str]:
        """Drop all indexes"""
        if not self.driver:
            return False, "No database connection"
        
        try:
            with self.driver.session(database=self.database) as session:
                result = session.run("SHOW INDEXES")
                indexes = list(result)
                
                for index in indexes:
                    index_name = index.get("name")
                    if index_name and not index_name.startswith("__"):
                        session.run(f"DROP INDEX {index_name} IF EXISTS")
                
                logger.info(f"[OK] Dropped {len(indexes)} indexes")
                return True, f"Dropped {len(indexes)} indexes"
        except Exception as e:
            logger.error(f"[ERROR] Failed to drop indexes: {str(e)}")
            return False, str(e)
    
    def reset_database(self, recreate_indexes: bool = True) -> Dict[str, Any]:
        """
        Complete database reset:
        1. Delete all nodes and relationships
        2. Drop all indexes
        3. Recreate indexes (optional)
        """
        stats_before = self.get_schema_stats()
        
        # Delete all data
        success, msg = self.delete_all_nodes_and_relationships()
        if not success:
            return {
                "status": "FAIL",
                "message": f"Failed to delete data: {msg}",
                "before": stats_before.__dict__ if stats_before else {}
            }
        
        # Drop indexes
        success, msg = self.drop_all_indexes()
        
        # Recreate indexes
        if recreate_indexes:
            success, msg = self.create_indexes()
        
        stats_after = self.get_schema_stats()
        
        return {
            "status": "SUCCESS",
            "message": "Database reset complete",
            "before": {
                "nodes": stats_before.total_nodes,
                "relationships": stats_before.total_relationships
            },
            "after": {
                "nodes": stats_after.total_nodes,
                "relationships": stats_after.total_relationships
            }
        }
    
    def print_schema_report(self):
        """Print detailed schema report"""
        stats = self.get_schema_stats()
        
        print("\n" + "="*80)
        print("NEO4J SCHEMA REPORT")
        print("="*80)
        print(f"Total Nodes: {stats.total_nodes}")
        print(f"Total Relationships: {stats.total_relationships}")
        
        if stats.node_types:
            print(f"\nNode Types ({len(stats.node_types)}):")
            for nt in stats.node_types:
                print(f"  - {nt}")
        
        if stats.relationship_types:
            print(f"\nRelationship Types ({len(stats.relationship_types)}):")
            for rt in stats.relationship_types:
                print(f"  - {rt}")
        
        if stats.indexes:
            print(f"\nIndexes ({len(stats.indexes)}):")
            for idx in stats.indexes:
                print(f"  - {idx}")
        
        if stats.constraints:
            print(f"\nConstraints ({len(stats.constraints)}):")
            for c in stats.constraints:
                print(f"  - {c}")
        
        print("="*80 + "\n")
    
    def close(self):
        """Close database connection"""
        if self.driver:
            self.driver.close()
            logger.info("[OK] Neo4j connection closed")


if __name__ == "__main__":
    # Test usage
    cleaner = Neo4jSchemaCleaner()
    
    print("\n[INFO] Current Schema Stats:")
    cleaner.print_schema_report()
    
    print("[INFO] Resetting database...")
    result = cleaner.reset_database()
    print(f"Result: {result}")
    
    print("\n[INFO] Updated Schema Stats:")
    cleaner.print_schema_report()
    
    cleaner.close()
