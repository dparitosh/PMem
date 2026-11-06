"""Manufacturing Process Recommender Service.

Given a part name, recommends manufacturing processes based on:
1. Direct process linkage — Process individuals in same PLMXMLFile
2. ProcessInstance chain — ProcessInstance → referencesProductInstance → ProductInstance
3. Process type classification — grouped by sourceTag
4. Related-part processes — processes used on assembly siblings
5. RFLP realization — processes for parts connected via realizes
"""

import logging
import re
from collections import defaultdict
from difflib import SequenceMatcher

from .recommendation_semantics import pick_semantic_source
from .recommendation_scope import cypher_scope_filter

logger = logging.getLogger(__name__)

TRACE_NODE_PATTERN = re.compile(r'^[A-Za-z]{1,3}[0-9A-Za-z_]{6,}$')


def _is_business_name(value: str) -> bool:
    text = str(value or '').strip()
    if not text:
        return False
    lower = text.lower()
    if lower.startswith('id'):
        return False
    if TRACE_NODE_PATTERN.fullmatch(text) and '_' in text:
        return False
    return SequenceMatcher(None, lower, 'process').ratio() < 1


class ManufacturingProcessRecommender:
    """Recommend manufacturing processes for a given part."""

    def __init__(self, graph):
        self._graph = graph

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def recommend(self, part_name: str, scope: dict | None = None, node_id: str | None = None) -> dict:
        """Return manufacturing process recommendations for *part_name*."""
        source = self._find_part_by_id(str(node_id), scope=scope) if node_id else None
        if not source:
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
        trace_context = self._find_traceability_process_context(source)
        related.extend(realizes_procs)
        related.extend(trace_context)
        if len(direct) + len(instances) + len(related) < 3:
            related.extend(self._find_contextual_process_candidates(source))

        # De-duplicate related
        seen = {p["process_name"] for p in direct}
        unique_related = []
        for rp in related:
            if rp["process_name"] not in seen:
                seen.add(rp["process_name"])
                unique_related.append(rp)

        # Summary by type
        summary = self._build_summary(direct, instances, unique_related)
        total_hits = len(direct) + len(instances) + len(unique_related)

        return {
            "part": {"name": source["name"], "source_tag": source.get("source_tag")},
            "direct_processes": direct,
            "process_instances": instances,
            "related_part_processes": unique_related,
            "process_summary": summary,
            "message": (
                None
                if total_hits > 0
                else "No process-like or operational context was found around this node in the current graph. Try a requirement, service activity, or operational object with richer traceability."
            ),
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _find_part_by_id(self, node_id: str, scope: dict | None = None) -> dict | None:
        if not node_id:
            return None
        scope_clause, scope_params = cypher_scope_filter("p", scope)
        rows = self._graph.query(
            """
            MATCH (p)
            WHERE elementId(p) = $node_id
            """ + scope_clause + """
            OPTIONAL MATCH (p)-[:INSTANCE_OF]->(cls:OntologyClass)
            RETURN p.name AS name, coalesce(cls.name, head(labels(p))) AS source_tag,
                   elementId(p) AS eid, cls.name AS class_name, labels(p) AS labels,
                   p.element_type AS element_type
            LIMIT 1
            """,
            params={"node_id": node_id, **scope_params},
        )
        if not rows:
            return None
        row = rows[0]
        return {
            "name": row.get("name"),
            "source_tag": row.get("source_tag"),
            "eid": row.get("eid"),
            "class_name": row.get("class_name"),
        }

    def _find_part(self, name: str, scope: dict | None = None) -> dict | None:
        scope_clause, scope_params = cypher_scope_filter("p", scope)
        rows = self._graph.query(
            """
            MATCH (p)
            WHERE toLower(p.name) CONTAINS toLower($name)
            """ + scope_clause + """
            OPTIONAL MATCH (p)-[:INSTANCE_OF]->(cls:OntologyClass)
            RETURN p.name AS name, coalesce(cls.name, head(labels(p))) AS source_tag,
                   elementId(p) AS eid, cls.name AS class_name, labels(p) AS labels,
                   p.element_type AS element_type
            LIMIT 25
            """,
            params={"name": name, **scope_params},
        )
        if not rows:
            return None
        best = pick_semantic_source(name, rows, prefer="part")
        return best

    def _find_direct_processes(self, source: dict) -> list[dict]:
        """Processes in the same PLMXMLFile as the part."""
        rows = self._graph.query(
            """
            MATCH (part) WHERE elementId(part) = $eid
            MATCH (part)-[:FND_TRACELINK|RELATEDREFS]-(bridge:GeneralRelation)-[:FND_TRACELINK|RELATEDREFS]-(proc)
            WHERE proc <> part
              AND proc.name IS NOT NULL
              AND NOT proc:GeneralRelation
            OPTIONAL MATCH (proc)-[:INSTANCE_OF]->(cls:OntologyClass)
            RETURN DISTINCT proc.name AS name, coalesce(cls.name, head(labels(proc))) AS source_tag,
                   cls.name AS type, NULL AS file_name
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
            MATCH (part) WHERE elementId(part) = $eid
            MATCH (part)-[:PART_REF|PARTREF|PRODUCT_REF|REVISIONREF|INSTANCEDREF]-(bi)
            WHERE bi.name IS NOT NULL
            RETURN DISTINCT bi.name AS name, head(labels(bi)) AS source_tag,
                   part.name AS references_instance
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
            MATCH (part) WHERE elementId(part) = $eid
            MATCH (part)-[:MASTER_REF|MASTERREF|PART_REF|PARTREF|PRODUCT_REF|REVISIONREF|INSTANCEDREF]-(sib)
            WHERE sib <> part AND sib.name IS NOT NULL
            MATCH (sib)-[:FND_TRACELINK|RELATEDREFS]-(bridge:GeneralRelation)-[:FND_TRACELINK|RELATEDREFS]-(proc)
            WHERE proc.name IS NOT NULL AND NOT proc:GeneralRelation
            OPTIONAL MATCH (proc)-[:INSTANCE_OF]->(cls:OntologyClass)
            RETURN DISTINCT proc.name AS process_name, sib.name AS part_name,
                   coalesce(cls.name, head(labels(proc))) AS source_tag
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
            MATCH (part) WHERE elementId(part) = $eid
            MATCH (part)-[:FND_TRACELINK|RELATEDREFS|SEG0SATISFY]-(connected)
            WHERE connected.name IS NOT NULL AND NOT connected:GeneralRelation
            OPTIONAL MATCH (connected)-[:INSTANCE_OF]->(cls:OntologyClass)
            RETURN DISTINCT connected.name AS process_name, part.name AS part_name,
                   coalesce(cls.name, head(labels(connected))) AS source_tag
            LIMIT 30
            """,
            params={"eid": source["eid"]},
        )
        return [
            {"process_name": r["process_name"], "part_name": r.get("part_name"),
             "source_tag": r.get("source_tag"), "relation": "realization_chain"}
            for r in rows if r.get("process_name")
        ]

    def _find_traceability_process_context(self, source: dict) -> list[dict]:
        """Process-like business objects connected through traceability bridge nodes."""
        rows = self._graph.query(
            """
            MATCH (part) WHERE elementId(part) = $eid
            MATCH (part)-[:FND_TRACELINK|RELATEDREFS]-(bridge:GeneralRelation)-[:FND_TRACELINK|RELATEDREFS]-(ctx)
            WHERE ctx <> part
              AND coalesce(ctx.name, '') <> ''
              AND NOT ctx:GeneralRelation
              AND NOT ctx:OntologyClass
              AND NOT ctx:ObjectProperty
              AND NOT ctx:DatatypeProperty
              AND NOT ctx:ProductInstance
              AND NOT ctx:ProductView
              AND NOT ctx:UserData
              AND NOT ctx:Transform
              AND NOT ctx:AttributeContext
            OPTIONAL MATCH (ctx)-[:INSTANCE_OF]->(cls:OntologyClass)
            RETURN DISTINCT
              coalesce(ctx.name, '') AS process_name,
              labels(ctx) AS labels,
              cls.name AS class_name,
              head(labels(ctx)) AS source_tag,
              CASE
                WHEN ctx:Requirement OR ctx:RequirementRevision THEN 'trace_requirement'
                WHEN ctx:Connection OR ctx:ConnectionRevision THEN 'connection_context'
                ELSE 'trace_context'
              END AS relation
            LIMIT 80
            """,
            params={'eid': source.get('eid')},
        ) or []
        results = []
        seen = set()
        process_terms = (
            'process', 'operation', 'activity', 'manufact', 'assemble', 'validate',
            'monitor', 'service', 'prepare', 'simulate', 'diagnos', 'clean', 'satisfy'
        )
        for row in rows:
            name = row.get('process_name')
            cls = str(row.get('class_name') or '').lower()
            labels = ' '.join(row.get('labels') or []).lower()
            lower_name = str(name or '').lower()
            if not _is_business_name(name):
                continue
            if not any(term in lower_name or term in cls or term in labels for term in process_terms):
                continue
            key = (lower_name, row.get('relation'))
            if key in seen:
                continue
            seen.add(key)
            results.append({
                'process_name': name,
                'part_name': source.get('name'),
                'source_tag': row.get('source_tag') or (row.get('labels') or [None])[0],
                'relation': row.get('relation') or 'trace_context',
            })
        return results

    def _find_contextual_process_candidates(self, source: dict) -> list[dict]:
        rows = self._graph.query(
            """
            MATCH (part) WHERE elementId(part) = $eid
            MATCH path = (part)-[*1..4]-(ctx)
            WHERE ctx <> part
              AND coalesce(ctx.name, '') <> ''
              AND NOT ctx:GeneralRelation
              AND NOT ctx:OntologyClass
              AND NOT ctx:ObjectProperty
              AND NOT ctx:DatatypeProperty
              AND NOT ctx:ProductInstance
              AND NOT ctx:ProductView
              AND NOT ctx:UserData
              AND NOT ctx:Transform
              AND NOT ctx:AttributeContext
            OPTIONAL MATCH (ctx)-[:INSTANCE_OF]->(cls:OntologyClass)
            RETURN DISTINCT
              coalesce(ctx.name, '') AS process_name,
              cls.name AS class_name,
              labels(ctx) AS labels,
              head(labels(ctx)) AS source_tag,
              length(path) AS hop_count
            LIMIT 120
            """,
            params={'eid': source.get('eid')},
        ) or []
        results = []
        seen = set()
        process_terms = ('process', 'operation', 'activity', 'manufact', 'assemble', 'validate', 'monitor', 'service', 'prepare', 'simulate', 'diagnos', 'clean')
        for row in rows:
            name = row.get('process_name')
            cls = str(row.get('class_name') or '').lower()
            labels = ' '.join(row.get('labels') or []).lower()
            lower_name = str(name or '').lower()
            if not _is_business_name(name):
                continue
            if not any(term in cls or term in lower_name or term in labels for term in process_terms):
                continue
            if lower_name in seen:
                continue
            seen.add(lower_name)
            results.append({
                'process_name': name,
                'part_name': source.get('name'),
                'source_tag': row.get('source_tag'),
                'relation': f'context_hop_{row.get("hop_count")}',
            })
            if len(results) >= 20:
                break
        return results

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
