"""Bounded read-only SPARQL over one governed Neo4j ontology projection."""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

from rdflib import Graph, Literal, Namespace, RDF, RDFS, URIRef

from .neo4j_publisher import publisher


DEPO = Namespace("urn:depo:graph:")
_BLOCKED = re.compile(r"\b(insert|delete|load|clear|create|drop|copy|move|add|service)\b", re.IGNORECASE)


class BoundedSparqlService:
    max_projection_nodes = 2_000
    max_results = 200

    @staticmethod
    def _predicate(value: str) -> URIRef:
        return URIRef(value) if value.startswith(("http://", "https://", "urn:")) else URIRef(f"urn:depo:relationship:{quote(value, safe='-._~')}")

    @staticmethod
    def _binding(value: Any) -> dict[str, Any]:
        if isinstance(value, URIRef):
            return {"type": "uri", "value": str(value)}
        if isinstance(value, Literal):
            result = {"type": "literal", "value": str(value)}
            if value.language: result["xml:lang"] = value.language
            if value.datatype: result["datatype"] = str(value.datatype)
            return result
        return {"type": "literal", "value": str(value)}

    def execute(self, *, ontology_id: str, query: str, limit: int = 200) -> dict[str, Any]:
        document = str(query or "").strip()
        if not ontology_id.strip():
            raise ValueError("ontology_id is required")
        if not document or len(document) > 10_000:
            raise ValueError("query is required and must be at most 10000 characters")
        if _BLOCKED.search(document) or not re.match(r"^(?:PREFIX\s+[^\n]+\s*)*(SELECT|ASK)\b", document, re.IGNORECASE):
            raise ValueError("Only read-only SELECT or ASK queries without SERVICE are allowed")
        projection_limit = max(1, min(int(limit), self.max_results))
        projection = publisher.projection(ontology_id=ontology_id, limit=self.max_projection_nodes)
        graph = Graph()
        for node in projection["nodes"]:
            iri = URIRef(str(node["id"])); graph.add((iri, RDFS.label, Literal(str(node.get("label") or node["id"]))))
            graph.add((iri, RDF.type, URIRef(f"urn:depo:kind:{quote(str(node.get('type') or 'resource'), safe='-._~')}")))
            graph.add((iri, DEPO.ontologyId, Literal(ontology_id)))
        for edge in projection["edges"]:
            graph.add((URIRef(str(edge["source"])), self._predicate(str(edge.get("predicate") or edge.get("type") or "RELATED_TO")), URIRef(str(edge["target"]))))
        result = graph.query(document)
        evidence = {"ontology_id": ontology_id, "projection_nodes": len(projection["nodes"]), "projection_edges": len(projection["edges"]), "projection_truncated": projection["truncated"]}
        if str(result.type) == "ASK":
            return {"head": {}, "boolean": bool(result.askAnswer), "evidence": evidence, "authorized_scope": "read-only"}
        variables = [str(value) for value in result.vars]
        bindings = []
        for row in result:
            bindings.append({variables[index]: self._binding(value) for index, value in enumerate(row) if value is not None})
            if len(bindings) >= projection_limit:
                break
        return {"head": {"vars": variables}, "results": {"bindings": bindings}, "count": len(bindings), "truncated": len(bindings) >= projection_limit, "evidence": evidence, "authorized_scope": "read-only"}


sparql = BoundedSparqlService()
