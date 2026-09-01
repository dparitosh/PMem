"""Direct, bounded Neo4j write boundary for the ingestion service."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from neo4j import GraphDatabase, Query


@dataclass(frozen=True)
class GraphStoreConfig:
    provider: str
    uri: str
    username: str
    password: str
    database: str

    @classmethod
    def from_env(cls) -> "GraphStoreConfig":
        provider = os.getenv("SEMANTIC_GRAPH_PROVIDER", "neo4j").strip().lower()
        if provider not in {"neo4j", "rapidminer", "oracle"}:
            raise ValueError("SEMANTIC_GRAPH_PROVIDER must be neo4j, rapidminer, or oracle")
        if provider == "neo4j":
            return cls(provider, os.getenv("NEO4J_URI", "neo4j://127.0.0.1:7687"), os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASS", ""), os.getenv("NEO4J_DATABASE", "ontology"))
        if provider == "rapidminer":
            return cls(provider, os.getenv("RAPIDMINER_SEMANTIC_GRAPH_URL", ""), os.getenv("RAPIDMINER_USER", ""), os.getenv("RAPIDMINER_TOKEN", ""), os.getenv("RAPIDMINER_SEMANTIC_GRAPH_DATABASE", ""))
        return cls(provider, os.getenv("ORACLE_SEMANTIC_GRAPH_DSN", ""), os.getenv("ORACLE_USER", ""), os.getenv("ORACLE_PASSWORD", ""), os.getenv("ORACLE_SEMANTIC_GRAPH_MODEL", ""))


class GraphStoreWriter:
    def __init__(self) -> None:
        self.config = GraphStoreConfig.from_env()
        self.timeout = int(os.getenv("NEO4J_IMPORT_QUERY_TIMEOUT", "600"))

    def execute(self, statement: str, parameters: dict[str, Any] | None = None) -> None:
        if self.config.provider != "neo4j":
            raise RuntimeError(
                f"The current tabular Cypher writer cannot execute against {self.config.provider}. "
                "Use a provider-specific canonical graph adapter before enabling this store."
            )
        if not self.config.password:
            raise RuntimeError("NEO4J_PASS is not configured")
        with GraphDatabase.driver(self.config.uri, auth=(self.config.username, self.config.password)) as driver:
            with driver.session(database=self.config.database) as session:
                session.run(Query(statement, timeout=float(self.timeout)), parameters or {}).consume()


writer = GraphStoreWriter()
