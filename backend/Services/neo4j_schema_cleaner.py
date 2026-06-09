r"""
Neo4j Schema Cleaner & Management Service
Cleans and manages Neo4j schema for testing and production use

✅ Uses centralized database configuration from backend/core/db_config.py
"""

import logging
import os
import re
from pathlib import Path
from typing import Dict, List, Any, Tuple
from neo4j import GraphDatabase, Driver
from dataclasses import dataclass
from dotenv import load_dotenv

# ✅ Import centralized database configuration
try:
    from backend.core.db_config import get_config, get_driver
    CENTRALIZED_CONFIG_AVAILABLE = True
except ImportError:
    try:
        from core.db_config import get_config, get_driver
        CENTRALIZED_CONFIG_AVAILABLE = True
    except ImportError:
        CENTRALIZED_CONFIG_AVAILABLE = False

# Load environment variables
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

logger = logging.getLogger(__name__)
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass
class SchemaStats:
    """Schema statistics"""
    total_nodes: int
    total_relationships: int
    node_types: List[str]
    relationship_types: List[str]
    indexes: List[str]
    constraints: List[str]


def _get_env(*keys: str) -> str | None:
    """Get first available environment variable"""
    for key in keys:
        value = os.getenv(key)
        if value:
            return value.strip()
    return None


def _reject_placeholder_uri(uri: str) -> None:
    if "your-neo4j-instance" in uri:
        raise ValueError(
            "NEO4J_URI still points to 'your-neo4j-instance'. "
            "Update backend/.env with the real Neo4j URI before cleaning schema."
        )


def _safe_identifier(value: str, kind: str) -> str:
    """Validate a Neo4j label/property/type identifier before interpolation."""
    cleaned = (value or "").strip()
    if not _IDENTIFIER_RE.fullmatch(cleaned):
        raise ValueError(
            f"Invalid Neo4j {kind}: {value!r}. Use letters, numbers, and underscores; "
            "the first character must be a letter or underscore."
        )
    return cleaned


def _safe_batch_size(value: int) -> int:
    try:
        batch_size = int(value)
    except Exception as exc:
        raise ValueError("Batch size must be an integer.") from exc
    if batch_size < 100 or batch_size > 50000:
        raise ValueError("Batch size must be between 100 and 50000.")
    return batch_size


class Neo4jSchemaCleaner:
    r"""
    Neo4j Schema Cleaner for test data cleanup and schema management
    Supports:
    - Full database wipe
    - Selective node/relationship deletion
    - Index management
    - Constraint management
    - Schema statistics
    
    ✅ Uses centralized configuration when available
    """
    
    def __init__(self, uri: str = None, username: str = None, password: str = None, database: str = None):
        """
        Initialize Neo4j connection
        
        Args:
            uri: Neo4j connection URI (default: from centralized config or NEO4J_URI env)
            username: Neo4j username (default: from centralized config or NEO4J_USER env)
            password: Neo4j password (default: from centralized config or NEO4J_PASS env)
            database: Neo4j database name (default: from centralized config or NEO4J_DATABASE env)
        """
        self.driver: Driver = None
        
        # Try to use centralized configuration first
        if CENTRALIZED_CONFIG_AVAILABLE and uri is None:
            try:
                config = get_config()
                self.uri = config.uri
                self.username = config.username
                self.password = config.password
                self.database = config.database
                logger.info("Using centralized Neo4j configuration")
            except Exception as e:
                logger.warning(f"Failed to use centralized config: {e}. Falling back to env vars.")
                self.uri = uri or _get_env("NEO4J_URI", "NEO4J_URL") or "bolt://localhost:7687"
                self.username = username or _get_env("NEO4J_USER", "NEO4J_USERNAME") or "neo4j"
                self.password = password or _get_env("NEO4J_PASS", "NEO4J_PASSWORD")
                self.database = database or _get_env("NEO4J_DATABASE") or "neo4j"
        else:
            # Use provided values or environment variables
            self.uri = uri or _get_env("NEO4J_URI", "NEO4J_URL") or "bolt://localhost:7687"
            self.username = username or _get_env("NEO4J_USER", "NEO4J_USERNAME") or "neo4j"
            self.password = password or _get_env("NEO4J_PASS", "NEO4J_PASSWORD")
            self.database = database or _get_env("NEO4J_DATABASE") or "neo4j"

        _reject_placeholder_uri(self.uri)
        if not self.password:
            raise ValueError("NEO4J_PASS or NEO4J_PASSWORD is required before cleaning schema.")
        
        try:
            # Try to use centralized driver if available
            if CENTRALIZED_CONFIG_AVAILABLE:
                try:
                    self.driver = get_driver()
                    logger.info("[OK] Using centralized Neo4j driver")
                except Exception as e:
                    logger.warning(f"Failed to use centralized driver: {e}. Creating new driver.")
                    self.driver = GraphDatabase.driver(self.uri, auth=(self.username, self.password))
            else:
                self.driver = GraphDatabase.driver(self.uri, auth=(self.username, self.password))
            
            # Test connection
            with self.driver.session(database=self.database) as session:
                result = session.run("RETURN 1")
                _ = result.single()
            logger.info("[OK] Neo4j connection established")
        except Exception as e:
            logger.error(f"[ERROR] Neo4j connection failed: {str(e)}")
            raise RuntimeError(f"Neo4j connection failed: {e}") from e
    
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
    
    def delete_all_nodes_and_relationships(self, batch_size: int = 10000) -> Tuple[bool, str]:
        """
        Delete ALL nodes and relationships from database
        WARNING: This is destructive and cannot be undone!
        """
        if not self.driver:
            return False, "No database connection"
        
        try:
            batch_size = _safe_batch_size(batch_size)
            with self.driver.session(database=self.database) as session:
                rel_record = session.run("MATCH ()-[r]->() RETURN count(r) as count").single()
                node_record = session.run("MATCH (n) RETURN count(n) as count").single()
                rel_deleted = rel_record["count"] if rel_record else 0
                node_deleted = node_record["count"] if node_record else 0

                if node_deleted:
                    session.run(f"""
                    MATCH (n)
                    CALL (n) {{
                        DETACH DELETE n
                    }} IN TRANSACTIONS OF {batch_size} ROWS
                    """).consume()
                
                logger.warning(f"[WARN] Deleted {node_deleted} nodes and {rel_deleted} relationships")
                return True, f"Deleted {node_deleted} nodes, {rel_deleted} relationships"
        except Exception as e:
            logger.error(f"[ERROR] Failed to delete nodes: {str(e)}")
            return False, str(e)
    
    def delete_nodes_by_type(self, node_type: str, batch_size: int = 10000) -> Tuple[bool, str]:
        """Delete all nodes of a specific label in batches."""
        if not self.driver:
            return False, "No database connection"
        
        try:
            node_type = _safe_identifier(node_type, "label")
            batch_size = _safe_batch_size(batch_size)
            with self.driver.session(database=self.database) as session:
                result = session.run(f"MATCH (n:`{node_type}`) RETURN count(n) as count")
                record = result.single()
                count = record["count"] if record else 0
                if count:
                    session.run(f"""
                    MATCH (n:`{node_type}`)
                    CALL (n) {{
                        DETACH DELETE n
                    }} IN TRANSACTIONS OF {batch_size} ROWS
                    """).consume()
                logger.info(f"[OK] Deleted {count} nodes of type {node_type}")
                return True, f"Deleted {count} {node_type} nodes"
        except Exception as e:
            logger.error(f"[ERROR] Failed to delete {node_type} nodes: {str(e)}")
            return False, str(e)

    def delete_nodes_by_label_property(
        self,
        label: str,
        property_name: str | None = None,
        property_value: Any | None = None,
        batch_size: int = 10000,
    ) -> Dict[str, Any]:
        """Delete nodes by label and optional property equality using batched transactions."""
        if not self.driver:
            return {"status": "FAIL", "message": "No database connection", "deleted_nodes": 0}

        label = _safe_identifier(label, "label")
        batch_size = _safe_batch_size(batch_size)
        has_property_filter = bool(property_name)
        property_clause = ""
        params: Dict[str, Any] = {}
        if has_property_filter:
            property_name = _safe_identifier(property_name or "", "property")
            property_clause = f"WHERE n.`{property_name}` = $property_value"
            params["property_value"] = property_value

        count_query = f"MATCH (n:`{label}`) {property_clause} RETURN count(n) AS count"
        delete_query = f"""
        MATCH (n:`{label}`)
        {property_clause}
        CALL (n) {{
            DETACH DELETE n
        }} IN TRANSACTIONS OF {batch_size} ROWS
        """

        try:
            with self.driver.session(database=self.database) as session:
                before_record = session.run(count_query, params).single()
                before_count = before_record["count"] if before_record else 0
                if before_count:
                    session.run(delete_query, params).consume()
                after_record = session.run(count_query, params).single()
                after_count = after_record["count"] if after_record else 0
                deleted = max(0, before_count - after_count)
                return {
                    "status": "SUCCESS",
                    "message": f"Deleted {deleted} nodes with label {label}",
                    "label": label,
                    "property": property_name if has_property_filter else "",
                    "property_value": property_value if has_property_filter else None,
                    "batch_size": batch_size,
                    "matched_before": before_count,
                    "matched_after": after_count,
                    "deleted_nodes": deleted,
                }
        except Exception as e:
            logger.error(f"[ERROR] Failed batched delete for label {label}: {str(e)}")
            return {
                "status": "FAIL",
                "message": str(e),
                "label": label,
                "property": property_name if has_property_filter else "",
                "deleted_nodes": 0,
            }

    def count_nodes_by_label_property(
        self,
        label: str,
        property_name: str | None = None,
        property_value: Any | None = None,
    ) -> Dict[str, Any]:
        """Preview the number of nodes matching a label/property cleanup filter."""
        if not self.driver:
            return {"status": "FAIL", "message": "No database connection", "matched_nodes": 0}

        label = _safe_identifier(label, "label")
        has_property_filter = bool(property_name)
        property_clause = ""
        params: Dict[str, Any] = {}
        if has_property_filter:
            property_name = _safe_identifier(property_name or "", "property")
            property_clause = f"WHERE n.`{property_name}` = $property_value"
            params["property_value"] = property_value

        count_query = f"MATCH (n:`{label}`) {property_clause} RETURN count(n) AS count"
        try:
            with self.driver.session(database=self.database) as session:
                record = session.run(count_query, params).single()
                matched = record["count"] if record else 0
                return {
                    "status": "SUCCESS",
                    "message": f"Matched {matched} nodes with label {label}",
                    "label": label,
                    "property": property_name if has_property_filter else "",
                    "property_value": property_value if has_property_filter else None,
                    "matched_nodes": matched,
                }
        except Exception as e:
            logger.error(f"[ERROR] Failed delete preview for label {label}: {str(e)}")
            return {
                "status": "FAIL",
                "message": str(e),
                "label": label,
                "property": property_name if has_property_filter else "",
                "matched_nodes": 0,
            }

    def delete_nodes_by_prefix(
        self,
        prefix: str,
        batch_size: int = 10000,
    ) -> Dict[str, Any]:
        """Delete nodes whose ontology_prefix or prefix matches the supplied value."""
        if not self.driver:
            return {"status": "FAIL", "message": "No database connection", "deleted_nodes": 0}

        prefix = str(prefix or "").strip()
        if not prefix:
            raise ValueError("Prefix is required.")
        if len(prefix) > 100:
            raise ValueError("Prefix must be 100 characters or fewer.")
        batch_size = _safe_batch_size(batch_size)
        params = {"prefix": prefix}
        filter_clause = "WHERE coalesce(n.ontology_prefix, n.prefix) = $prefix"
        count_query = f"MATCH (n) {filter_clause} RETURN count(n) AS count"
        delete_query = f"""
        MATCH (n)
        {filter_clause}
        CALL (n) {{
            DETACH DELETE n
        }} IN TRANSACTIONS OF {batch_size} ROWS
        """

        try:
            with self.driver.session(database=self.database) as session:
                before_record = session.run(count_query, params).single()
                before_count = before_record["count"] if before_record else 0
                if before_count:
                    session.run(delete_query, params).consume()
                after_record = session.run(count_query, params).single()
                after_count = after_record["count"] if after_record else 0
                deleted = max(0, before_count - after_count)
                return {
                    "status": "SUCCESS",
                    "message": f"Deleted {deleted} nodes with prefix {prefix}",
                    "prefix": prefix,
                    "batch_size": batch_size,
                    "matched_before": before_count,
                    "matched_after": after_count,
                    "deleted_nodes": deleted,
                }
        except Exception as e:
            logger.error(f"[ERROR] Failed batched delete for prefix {prefix}: {str(e)}")
            return {
                "status": "FAIL",
                "message": str(e),
                "prefix": prefix,
                "deleted_nodes": 0,
            }

    def count_nodes_by_prefix(self, prefix: str) -> Dict[str, Any]:
        """Preview nodes whose ontology_prefix or prefix matches the supplied value."""
        if not self.driver:
            return {"status": "FAIL", "message": "No database connection", "matched_nodes": 0}

        prefix = str(prefix or "").strip()
        if not prefix:
            raise ValueError("Prefix is required.")
        if len(prefix) > 100:
            raise ValueError("Prefix must be 100 characters or fewer.")

        params = {"prefix": prefix}
        filter_clause = "WHERE coalesce(n.ontology_prefix, n.prefix) = $prefix"
        count_query = f"MATCH (n) {filter_clause} RETURN count(n) AS count"
        try:
            with self.driver.session(database=self.database) as session:
                record = session.run(count_query, params).single()
                matched = record["count"] if record else 0
                return {
                    "status": "SUCCESS",
                    "message": f"Matched {matched} nodes with prefix {prefix}",
                    "prefix": prefix,
                    "matched_nodes": matched,
                }
        except Exception as e:
            logger.error(f"[ERROR] Failed delete preview for prefix {prefix}: {str(e)}")
            return {
                "status": "FAIL",
                "message": str(e),
                "prefix": prefix,
                "matched_nodes": 0,
            }
    
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
    
    def drop_all_constraints(self) -> Tuple[bool, str]:
        """Drop all non-system constraints."""
        if not self.driver:
            return False, "No database connection"

        try:
            with self.driver.session(database=self.database) as session:
                constraints = list(session.run("SHOW CONSTRAINTS"))
                dropped = 0
                for constraint in constraints:
                    constraint_name = constraint.get("name")
                    if constraint_name and not constraint_name.startswith("__"):
                        session.run(f"DROP CONSTRAINT `{constraint_name}` IF EXISTS").consume()
                        dropped += 1

                logger.info("[OK] Dropped %d constraints", dropped)
                return True, f"Dropped {dropped} constraints"
        except Exception as e:
            logger.error(f"[ERROR] Failed to drop constraints: {str(e)}")
            return False, str(e)

    def drop_all_indexes(self) -> Tuple[bool, str]:
        """Drop all non-system indexes."""
        if not self.driver:
            return False, "No database connection"

        try:
            with self.driver.session(database=self.database) as session:
                indexes = list(session.run("SHOW INDEXES"))
                dropped = 0
                for index in indexes:
                    index_name = index.get("name")
                    index_type = str(index.get("type") or "").upper()
                    if index_name and index_type != "LOOKUP" and not index_name.startswith("__"):
                        session.run(f"DROP INDEX `{index_name}` IF EXISTS").consume()
                        dropped += 1

                logger.info("[OK] Dropped %d indexes", dropped)
                return True, f"Dropped {dropped} indexes"
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
        
        # Drop constraints before indexes because constraints can own backing indexes.
        success, msg = self.drop_all_constraints()
        if not success:
            return {
                "status": "FAIL",
                "message": f"Failed to drop constraints: {msg}",
                "before": stats_before.__dict__ if stats_before else {}
            }

        success, msg = self.drop_all_indexes()
        if not success:
            return {
                "status": "FAIL",
                "message": f"Failed to drop indexes: {msg}",
                "before": stats_before.__dict__ if stats_before else {}
            }
        
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
        
        logger.info("%s", "="*80)
        logger.info("NEO4J SCHEMA REPORT")
        logger.info("%s", "="*80)
        logger.info("Total Nodes: %d", stats.total_nodes)
        logger.info("Total Relationships: %d", stats.total_relationships)

        if stats.node_types:
            logger.info("Node Types (%d):", len(stats.node_types))
            for nt in stats.node_types:
                logger.info("  - %s", nt)

        if stats.relationship_types:
            logger.info("Relationship Types (%d):", len(stats.relationship_types))
            for rt in stats.relationship_types:
                logger.info("  - %s", rt)

        if stats.indexes:
            logger.info("Indexes (%d):", len(stats.indexes))
            for idx in stats.indexes:
                logger.info("  - %s", idx)

        if stats.constraints:
            logger.info("Constraints (%d):", len(stats.constraints))
            for c in stats.constraints:
                logger.info("  - %s", c)

        logger.info("%s", "="*80)
    
    def close(self):
        """Close database connection"""
        if self.driver:
            self.driver.close()
            logger.info("[OK] Neo4j connection closed")


if __name__ == "__main__":
    # Test usage
    cleaner = Neo4jSchemaCleaner()
    
    logger.info("Current Schema Stats:")
    cleaner.print_schema_report()
    
    logger.info("Resetting database...")
    result = cleaner.reset_database()
    logger.info("Result: %s", result)
    
    logger.info("Updated Schema Stats:")
    cleaner.print_schema_report()
    
    cleaner.close()
