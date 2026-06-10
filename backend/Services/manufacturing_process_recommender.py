"""Manufacturing Process Recommender Service.

Given a part name, recommends manufacturing processes based on:
1. Direct process linkage — Process individuals in same PLMXMLFile
2. ProcessInstance chain — ProcessInstance → referencesProductInstance → ProductInstance
3. Process type classification — grouped by sourceTag
4. Related-part processes — processes used on assembly siblings
5. RFLP realization — processes for parts connected via realizes
"""

import logging
from collections import defaultdict
from difflib import SequenceMatcher

from .recommendation_scope import cypher_scope_filter

logger = logging.getLogger(__name__)


class ManufacturingProcessRecommender:
    """Recommend manufacturing processes for a given part."""

    def __init__(self, graph):
        self._graph = graph

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def recommend(self, part_name: str, scope: dict | None = None) -> dict:
        """Return manufacturing process recommendations for *part_name*."""
        source = self._find_part(part_name, scope=scope)
        if not source:
            return {
                "part": None,
                "direct_processes": [],
                "process_instances": [],
                "related_part_processes": [],
                "process_summary": {},
                "message": f"Part '{part_name}' not found",
            }

        direct = self._find_direct_processes(source)
        instances = self._find_process_instances(source)
        related = self._find_related_part_processes(source)
        realizes_procs = self._find_realizes_processes(source)
        related.extend(realizes_procs)

        # De-duplicate related
        seen = {p["process_name"] for p in direct}
        unique_related = []
        for rp in related:
            if rp["process_name"] not in seen:
                seen.add(rp["process_name"])
                unique_related.append(rp)

        # Summary by type
        summary = self._build_summary(direct, instances, unique_related)

        return {
            "part": {"name": source["name"], "source_tag": source.get("source_tag")},
            "direct_processes": direct,
            "process_instances": instances,
            "related_part_processes": unique_related,
            "process_summary": summary,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _find_part(self, name: str, scope: dict | None = None) -> dict | None:
        scope_clause, scope_params = cypher_scope_filter("p", scope)
        rows = self._graph.query(
            """
            MATCH (p:Individual)
            WHERE toLower(p.name) CONTAINS toLower($name)
            """ + scope_clause + """
            OPTIONAL MATCH (p)-[:INSTANCE_OF]->(cls:OntologyClass)
            RETURN p.name AS name, p.sourceTag AS source_tag,
                   elementId(p) AS eid, cls.name AS class_name
            LIMIT 5
            """,
            params={"name": name, **scope_params},
        )
        if not rows:
            return None
        best = max(rows, key=lambda r: SequenceMatcher(None, name.lower(), (r["name"] or "").lower()).ratio())
        return best

    def _find_direct_processes(self, source: dict) -> list[dict]:
        """Processes in the same PLMXMLFile as the part."""
        rows = self._graph.query(
            """
            MATCH (part:Individual) WHERE elementId(part) = $eid
            MATCH (file:Individual)-[:contains]->(part)
            MATCH (file)-[:contains]->(proc:Individual)
                  -[:INSTANCE_OF]->(:OntologyClass {name: 'Process'})
            RETURN DISTINCT proc.name AS name, proc.sourceTag AS source_tag,
                   proc.type AS type, file.name AS file_name
            """,
            params={"eid": source["eid"]},
        )
        return [
            {"process_name": r["name"], "type": r.get("type"),
             "source_tag": r.get("source_tag"), "file_name": r.get("file_name")}
            for r in rows if r.get("name")
        ]

    def _find_process_instances(self, source: dict) -> list[dict]:
        """ProcessInstance → referencesProductInstance → ProductInstance for this part."""
        rows = self._graph.query(
            """
            MATCH (part:Individual) WHERE elementId(part) = $eid
            MATCH (file:Individual)-[:contains]->(part)
            MATCH (file)-[:contains]->(bi:Individual)
                  -[:INSTANCE_OF]->(:OntologyClass {name: 'ProductInstance'})
            MATCH (pi:Individual)-[:referencesProductInstance]->(bi)
            RETURN DISTINCT pi.name AS name, pi.sourceTag AS source_tag,
                   bi.name AS references_instance
            """,
            params={"eid": source["eid"]},
        )
        return [
            {"name": r["name"], "source_tag": r.get("source_tag"),
             "references_instance": r.get("references_instance")}
            for r in rows if r.get("name")
        ]

    def _find_related_part_processes(self, source: dict) -> list[dict]:
        """Processes for sibling nodes in the same PLMXMLFile."""
        rows = self._graph.query(
            """
            MATCH (part:Individual) WHERE elementId(part) = $eid
            MATCH (file:Individual)-[:contains]->(part)
            MATCH (file)-[:contains]->(sib:Individual)
            WHERE sib <> part AND sib.name IS NOT NULL
            MATCH (file2:Individual)-[:contains]->(sib)
            MATCH (file2)-[:contains]->(proc:Individual)
                  -[:INSTANCE_OF]->(:OntologyClass {name: 'Process'})
            RETURN DISTINCT proc.name AS process_name, sib.name AS part_name,
                   proc.sourceTag AS source_tag
            LIMIT 50
            """,
            params={"eid": source["eid"]},
        )
        return [
            {"process_name": r["process_name"], "part_name": r.get("part_name"),
             "source_tag": r.get("source_tag"), "relation": "assembly_sibling"}
            for r in rows if r.get("process_name")
        ]

    def _find_realizes_processes(self, source: dict) -> list[dict]:
        """Processes for nodes connected via realizes."""
        rows = self._graph.query(
            """
            MATCH (part:Individual) WHERE elementId(part) = $eid
            MATCH (part)-[:realizes|tracesTo]-(connected:Individual)
            WHERE connected.name IS NOT NULL
            MATCH (file:Individual)-[:contains]->(connected)
            MATCH (file)-[:contains]->(proc:Individual)
                  -[:INSTANCE_OF]->(:OntologyClass {name: 'Process'})
            RETURN DISTINCT proc.name AS process_name, connected.name AS part_name,
                   proc.sourceTag AS source_tag
            LIMIT 30
            """,
            params={"eid": source["eid"]},
        )
        return [
            {"process_name": r["process_name"], "part_name": r.get("part_name"),
             "source_tag": r.get("source_tag"), "relation": "realization_chain"}
            for r in rows if r.get("process_name")
        ]

    @staticmethod
    def _build_summary(direct, instances, related) -> dict:
        """Group processes by sourceTag type."""
        by_type = defaultdict(list)
        for p in direct:
            by_type[p.get("source_tag", "Unknown")].append(p["process_name"])
        return {
            "total_direct": len(direct),
            "total_instances": len(instances),
            "total_related": len(related),
            "by_type": dict(by_type),
        }
