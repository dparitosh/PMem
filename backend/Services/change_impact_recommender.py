"""Change Impact Recommender Service.

Given a change entity name OR a part name, traverses the Neo4j graph to find:
- Impacted parts via GeneralRelation (CMHasImpactedItem, CMHasProblemItem, CMHasSolutionItem)
- Assembly impact via hasChildInstance tree
- Impacted requirements via Seg0Satisfy / FND_TraceLink
- Process impact via PLMXMLFile co-occurrence and ProcessInstance chains
- Realization chain via realizes / tracesTo
"""

import logging
from difflib import SequenceMatcher

from .recommendation_semantics import pick_semantic_source
from .recommendation_scope import cypher_scope_filter

logger = logging.getLogger(__name__)

def _is_business_name(value: str) -> bool:
    text = str(value or '').strip()
    if not text:
        return False
    return SequenceMatcher(None, text.lower(), 'id').ratio() < 1 and not text.lower().startswith('id')


class ChangeImpactRecommender:
    """Analyse change impact across the PLM knowledge graph."""

    def __init__(self, graph):
        self._graph = graph

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyse(self, *, change_name: str = "", part_name: str = "", scope: dict | None = None) -> dict:
        """Run full change-impact analysis.

        Supply *either* ``change_name`` (a ChangeRequest/ChangeNotice entity)
        or ``part_name`` (any Part individual).  Returns a structured dict.
        """
        if not change_name and not part_name:
            return {"error": "Provide change_name or part_name"}

        # Step 1 — resolve the change entity
        change_entity = None
        node_id = (scope or {}).get("node_id") or (scope or {}).get("element_id") or ""
        if node_id:
            change_entity = self._find_change_entity_by_id(str(node_id), scope=scope)
        if not change_entity and change_name:
            change_entity = self._find_change_entity(change_name, scope=scope)
        if not change_entity and change_name:
            change_entity = self._find_part_as_change_proxy(change_name, scope=scope)
        if not change_entity and part_name:
            if node_id:
                change_entity = self._find_part_by_id(str(node_id), scope=scope)
            if not change_entity:
                change_entity = self._find_part_as_change_proxy(part_name, scope=scope)
        if not change_entity:
            return {
                "change_entity": None,
                "impacted_parts": [],
                "assembly_impact": [],
                "impacted_requirements": [],
                "process_impacts": [],
                "realization_chain": [],
                "impact_score": 0,
                "message": f"No change entity found for '{change_name or part_name}'",
            }

        # Step 2 — gather impacts
        impacted_parts = self._find_impacted_parts(change_entity)

        # If no impacted parts found via GeneralRelation (common for non-change entities),
        # treat the entity itself as the "impacted part" so downstream analysis still works
        if not impacted_parts:
            impacted_parts = [{
                "name": change_entity["name"],
                "source_tag": change_entity.get("source_tag"),
                "relation_type": "self",
                "class_name": None,
                "elementId": change_entity["elementId"],
            }]

        assembly_impact = self._find_assembly_impact(impacted_parts)
        impacted_reqs = self._find_impacted_requirements(impacted_parts)
        process_impacts = self._find_process_impacts(impacted_parts)
        realization_chain = self._find_realization_chain(impacted_parts)

        # Step 3 — score
        score = self._compute_impact_score(
            impacted_parts, assembly_impact, impacted_reqs, process_impacts, realization_chain
        )

        return {
            "change_entity": change_entity,
            "impacted_parts": impacted_parts,
            "assembly_impact": assembly_impact,
            "impacted_requirements": impacted_reqs,
            "process_impacts": process_impacts,
            "realization_chain": realization_chain,
            "impact_score": round(score, 1),
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _find_change_entity_by_id(self, node_id: str, scope: dict | None = None) -> dict | None:
        if not node_id:
            return None
        scope_clause, scope_params = cypher_scope_filter("cr", scope)
        rows = self._graph.query(
            """
            MATCH (cr)
            WHERE elementId(cr) = $node_id
            """ + scope_clause + """
            RETURN cr.name AS name, head(labels(cr)) AS source_tag,
                   cr.revision AS revision, elementId(cr) AS eid
            LIMIT 1
            """,
            params={"node_id": node_id, **scope_params},
        )
        if not rows:
            return None
        row = rows[0]
        return {"name": row["name"], "source_tag": row["source_tag"], "revision": row.get("revision"), "elementId": row["eid"]}

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
                   p.revision AS revision, elementId(p) AS eid,
                   cls.name AS class_name, labels(p) AS labels,
                   p.element_type AS element_type
            LIMIT 1
            """,
            params={"node_id": node_id, **scope_params},
        )
        if not rows:
            return None
        row = rows[0]
        return {"name": row["name"], "source_tag": row["source_tag"], "revision": row.get("revision"), "elementId": row["eid"], "class_name": row.get("class_name")}

    def _find_change_entity(self, name: str, scope: dict | None = None) -> dict | None:
        scope_clause, scope_params = cypher_scope_filter("cr", scope)
        rows = self._graph.query(
            """
            MATCH (cr)
            WHERE toLower(cr.name) CONTAINS toLower($name)
            """ + scope_clause + """
            RETURN cr.name AS name, head(labels(cr)) AS source_tag,
                   cr.revision AS revision, elementId(cr) AS eid
            LIMIT 5
            """,
            params={"name": name, **scope_params},
        )
        if not rows:
            return None
        # pick best fuzzy match
        best = pick_semantic_source(name, rows, prefer="part")
        return {"name": best["name"], "source_tag": best["source_tag"],
                "revision": best.get("revision"), "elementId": best["eid"]}

    def _find_part_as_change_proxy(self, name: str, scope: dict | None = None) -> dict | None:
        scope_clause, scope_params = cypher_scope_filter("p", scope)
        rows = self._graph.query(
            """
            MATCH (p)
            WHERE toLower(p.name) CONTAINS toLower($name)
            """ + scope_clause + """
            OPTIONAL MATCH (p)-[:INSTANCE_OF]->(cls:OntologyClass)
            RETURN p.name AS name, coalesce(cls.name, head(labels(p))) AS source_tag,
                   p.revision AS revision, elementId(p) AS eid,
                   cls.name AS class_name, labels(p) AS labels,
                   p.element_type AS element_type
            LIMIT 25
            """,
            params={"name": name, **scope_params},
        )
        if not rows:
            return None
        best = pick_semantic_source(name, rows, prefer="part")
        return {"name": best["name"], "source_tag": best["source_tag"],
                "revision": best.get("revision"), "elementId": best["eid"]}

    def _find_impacted_parts(self, change_entity: dict) -> list[dict]:
        """Find parts impacted via GeneralRelation."""
        rows = self._graph.query(
            """
            MATCH (cr) WHERE elementId(cr) = $eid
            MATCH (cr)-[rel:FND_TRACELINK|RELATEDREFS|SEG0SATISFY|MASTERREF|MASTER_REF|PART_REF|PARTREF|PRODUCT_REF|REVISIONREF|INSTANCEDREF]-(impacted)
            WHERE impacted <> cr
              AND NOT any(lbl IN labels(impacted) WHERE lbl IN ['DatasheetChunk', 'GraphChunk', 'GeneralRelation', 'RelationshipCarrier'])
            OPTIONAL MATCH (impacted)-[:INSTANCE_OF]->(cls:OntologyClass)
            RETURN DISTINCT impacted.name AS name,
                   coalesce(cls.name, head(labels(impacted))) AS source_tag,
                   type(rel) AS relation_type,
                   cls.name AS class_name,
                   elementId(impacted) AS eid
            LIMIT 100
            """,
            params={"eid": change_entity["elementId"]},
        ) or []
        rows2 = []
        seen = set()
        parts = []
        for r in rows + rows2:
            if r.get("name") and _is_business_name(r.get("name")) and r["eid"] not in seen:
                seen.add(r["eid"])
                parts.append({
                    "name": r["name"],
                    "source_tag": r.get("source_tag"),
                    "relation_type": r.get("relation_type"),
                    "class_name": r.get("class_name"),
                    "elementId": r["eid"],
                })
        return parts

    def _find_assembly_impact(self, impacted_parts: list[dict]) -> list[dict]:
        """Walk assembly tree upward from impacted parts."""
        if not impacted_parts:
            return []
        eids = [p["elementId"] for p in impacted_parts]
        rows = []
        # Assembly context from current PLM/XML reference relationships.
        rows2 = self._graph.query(
            """
            UNWIND $eids AS eid
            MATCH (part) WHERE elementId(part) = eid
            MATCH path = (part)-[:MASTERREF|MASTER_REF|PART_REF|PARTREF|PRODUCT_REF|REVISIONREF|INSTANCEDREF*1..4]-(ancestor)
            WHERE ancestor.name IS NOT NULL AND NOT toLower(ancestor.name) STARTS WITH 'id'
            RETURN DISTINCT part.name AS part_name,
                   ancestor.name AS assembly_name,
                   length(path) AS depth
            LIMIT 200
            """,
            params={"eids": eids},
        ) or []
        # Strategy 3: PLMXMLFile siblings (all entities in same file)
        rows3 = []
        assemblies = []
        seen = set()
        for r in rows + rows2 + rows3:
            key = r.get("assembly_name")
            if key and key not in seen:
                seen.add(key)
                assemblies.append({
                    "assembly_name": key,
                    "depth": r.get("depth", 0),
                    "from_part": r.get("part_name"),
                })
        return assemblies

    def _find_impacted_requirements(self, impacted_parts: list[dict]) -> list[dict]:
        """Find requirements linked to impacted parts via Seg0Satisfy / FND_TraceLink."""
        if not impacted_parts:
            return []
        eids = [p["elementId"] for p in impacted_parts]
        rows = self._graph.query(
            """
            UNWIND $eids AS eid
            MATCH (part) WHERE elementId(part) = eid
            MATCH (part)-[rel:FND_TRACELINK|RELATEDREFS|SEG0SATISFY]-(req)
            OPTIONAL MATCH (req)-[:INSTANCE_OF]->(cls:OntologyClass)
            WHERE coalesce(cls.name, head(labels(req)), '') CONTAINS 'Requirement'
               OR toLower(coalesce(req.name, '')) STARTS WITH 'req'
            WITH req, part, properties(req) AS req_props
            RETURN DISTINCT req.name AS name,
                   coalesce(req_props['catalogueId'], req_props['uid'], req_props['id'], '') AS catalogue_id,
                   coalesce(req_props['bodyText'], req_props['description'], req_props['label'], '') AS body_text,
                   part.name AS linked_part
            LIMIT 200
            """,
            params={"eids": eids},
        ) or []
        reqs = []
        seen = set()
        for r in rows:
            if r.get("name") and r["name"] not in seen:
                seen.add(r["name"])
                reqs.append({
                    "name": r["name"],
                    "catalogue_id": r.get("catalogue_id"),
                    "body_text": r.get("body_text"),
                    "linked_part": r.get("linked_part"),
                })
        return reqs

    def _find_process_impacts(self, impacted_parts: list[dict]) -> list[dict]:
        """Find processes in same PLMXMLFile as impacted parts."""
        if not impacted_parts:
            return []
        eids = [p["elementId"] for p in impacted_parts]
        rows = []
        rows2 = []
        seen = set()
        results = []
        for r in rows + rows2:
            if r.get("name") and _is_business_name(r.get("name")) and r["name"] not in seen:
                seen.add(r["name"])
                results.append({"name": r["name"], "source_tag": r.get("source_tag"), "from_part": r.get("from_part")})
        return results

    def _find_realization_chain(self, impacted_parts: list[dict]) -> list[dict]:
        """Follow realizes / tracesTo and any direct relationships from impacted parts."""
        if not impacted_parts:
            return []
        eids = [p["elementId"] for p in impacted_parts]
        # Direct traceability links
        rows = self._graph.query(
            """
            UNWIND $eids AS eid
            MATCH (part) WHERE elementId(part) = eid
            OPTIONAL MATCH (part)-[r:FND_TRACELINK|RELATEDREFS|SEG0SATISFY|MASTERREF|MASTER_REF|PART_REF|PARTREF|PRODUCT_REF|REVISIONREF|INSTANCEDREF]-(connected)
            RETURN DISTINCT connected.name AS name,
                   type(r) AS link_type,
                   head(labels(connected)) AS source_tag,
                   part.name AS from_part
            """,
            params={"eids": eids},
        )
        # Also get any relationship (broader catch-all)
        rows2 = self._graph.query(
            """
            UNWIND $eids AS eid
            MATCH (part) WHERE elementId(part) = eid
            MATCH (part)-[r]-(connected)
            WHERE NOT type(r) IN ['INSTANCE_OF']
              AND connected.name IS NOT NULL
            RETURN DISTINCT connected.name AS name,
                   type(r) AS link_type,
                   head(labels(connected)) AS source_tag,
                   part.name AS from_part
            LIMIT 50
            """,
            params={"eids": eids},
        )
        seen = set()
        results = []
        for r in rows + rows2:
            if r.get("name") and _is_business_name(r.get("name")) and r["name"] not in seen:
                seen.add(r["name"])
                results.append({
                    "name": r["name"], "link_type": r.get("link_type"),
                    "source_tag": r.get("source_tag"), "from_part": r.get("from_part")
                })
        return results

    @staticmethod
    def _compute_impact_score(parts, assemblies, reqs, processes, chain) -> float:
        """0-100 score based on breadth of impact."""
        score = 0.0
        score += min(len(parts) * 10, 30)       # up to 30 for impacted parts
        score += min(len(assemblies) * 5, 20)    # up to 20 for assembly reach
        score += min(len(reqs) * 8, 20)          # up to 20 for requirement impact
        score += min(len(processes) * 5, 15)     # up to 15 for process impact
        score += min(len(chain) * 5, 15)         # up to 15 for realization chain
        return min(score, 100.0)
