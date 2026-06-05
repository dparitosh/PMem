"""Similar Parts Recommender Service.

Given a part name, finds similar parts using weighted multi-factor scoring:
- sourceTag match      (20 pts) — same entity type
- rflpLayer match      (15 pts) — same RFLP layer
- Assembly co-occurrence (30 pts) — same PLMXMLFile or sibling ProductInstances
- Traceability link    (20 pts) — connected via tracesTo / realizes / linkedTo
- Name similarity      (15 pts) — shared keywords in name
"""

import logging
import re
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

# Stop-words stripped from names before keyword comparison
_STOP = frozenset({"the", "a", "an", "of", "for", "and", "in", "to", "with", "on", "at", "by", "is", "rev", "revision"})


class SimilarPartsRecommender:
    """Find parts similar to a given part using graph structure + properties."""

    def __init__(self, graph):
        self._graph = graph

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def recommend(self, part_name: str, top_n: int = 10) -> dict:
        """Return the top-N most similar parts to *part_name*."""
        source = self._find_source_part(part_name)
        if not source:
            return {
                "source_part": None,
                "similar_parts": [],
                "message": f"Part '{part_name}' not found",
            }

        candidates: dict[str, dict] = {}  # elementId -> info

        # Factor 1+2: same-file siblings (assembly co-occurrence)
        siblings = self._find_assembly_siblings(source)
        for s in siblings:
            candidates.setdefault(s["eid"], {**s, "assembly": True, "trace_link": None})
            candidates[s["eid"]]["assembly"] = True

        # Factor 3: traceability connections
        traced = self._find_traceability_connections(source)
        for t in traced:
            cand = candidates.setdefault(t["eid"], {**t, "assembly": False, "trace_link": t.get("link_type")})
            cand["trace_link"] = t.get("link_type")

        # Score every candidate
        scored = []
        for eid, info in candidates.items():
            score_detail = self._score(source, info)
            scored.append({
                "name": info.get("name"),
                "source_tag": info.get("source_tag"),
                "rflp_layer": info.get("rflp_layer"),
                "similarity_score": round(score_detail["total"], 1),
                "source_tag_match": score_detail["source_tag_match"],
                "rflp_layer_match": score_detail["rflp_layer_match"],
                "shared_assembly": info.get("assembly", False),
                "traceability_link": info.get("trace_link"),
                "score_breakdown": score_detail,
            })

        scored.sort(key=lambda x: x["similarity_score"], reverse=True)
        return {
            "source_part": {
                "name": source["name"],
                "source_tag": source.get("source_tag"),
                "rflp_layer": source.get("rflp_layer"),
            },
            "similar_parts": scored[:top_n],
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _find_source_part(self, name: str) -> dict | None:
        rows = self._graph.query(
            """
            MATCH (p:Individual)
            WHERE toLower(p.name) CONTAINS toLower($name)
            OPTIONAL MATCH (p)-[:INSTANCE_OF]->(cls:OntologyClass)
            RETURN p.name AS name, p.sourceTag AS source_tag,
                   p.rflpLayer AS rflp_layer, elementId(p) AS eid,
                   cls.name AS class_name
            LIMIT 5
            """,
            params={"name": name},
        )
        if not rows:
            return None
        best = max(rows, key=lambda r: SequenceMatcher(None, name.lower(), (r["name"] or "").lower()).ratio())
        return best

    def _find_assembly_siblings(self, source: dict) -> list[dict]:
        """Individuals sharing a PLMXMLFile with the source."""
        rows = self._graph.query(
            """
            MATCH (src:Individual) WHERE elementId(src) = $eid
            MATCH (file:Individual)-[:contains]->(src)
            MATCH (file)-[:contains]->(sib:Individual)
            WHERE sib <> src AND sib.name IS NOT NULL
            OPTIONAL MATCH (sib)-[:INSTANCE_OF]->(cls:OntologyClass)
            RETURN DISTINCT sib.name AS name, sib.sourceTag AS source_tag,
                   sib.rflpLayer AS rflp_layer, elementId(sib) AS eid,
                   cls.name AS class_name
            """,
            params={"eid": source["eid"]},
        )
        return rows

    def _find_traceability_connections(self, source: dict) -> list[dict]:
        """Parts connected via tracesTo, realizes, linkedTo, allocates."""
        rows = self._graph.query(
            """
            MATCH (src:Individual) WHERE elementId(src) = $eid
            MATCH (src)-[r:tracesTo|realizes|linkedTo|allocates]-(conn:Individual)
            WHERE conn <> src AND conn.name IS NOT NULL
            OPTIONAL MATCH (conn)-[:INSTANCE_OF]->(cls:OntologyClass)
            RETURN DISTINCT conn.name AS name, conn.sourceTag AS source_tag,
                   conn.rflpLayer AS rflp_layer, type(r) AS link_type,
                   elementId(conn) AS eid, cls.name AS class_name
            """,
            params={"eid": source["eid"]},
        )
        return rows

    def _score(self, source: dict, candidate: dict) -> dict:
        """Compute weighted similarity score (0-100)."""
        # sourceTag match (20 pts)
        st_match = (source.get("source_tag") or "").lower() == (candidate.get("source_tag") or "").lower()
        st_score = 20.0 if st_match else 0.0

        # rflpLayer match (15 pts)
        rl_match = bool(source.get("rflp_layer") and candidate.get("rflp_layer")
                        and source["rflp_layer"] == candidate["rflp_layer"])
        rl_score = 15.0 if rl_match else 0.0

        # Assembly co-occurrence (30 pts)
        asm_score = 30.0 if candidate.get("assembly") else 0.0

        # Traceability (20 pts)
        trace_score = 20.0 if candidate.get("trace_link") else 0.0

        # Name similarity (15 pts)
        name_score = self._name_similarity(source.get("name", ""), candidate.get("name", "")) * 15.0

        total = st_score + rl_score + asm_score + trace_score + name_score
        return {
            "total": min(total, 100.0),
            "source_tag_match": st_match,
            "source_tag_score": st_score,
            "rflp_layer_match": rl_match,
            "rflp_layer_score": rl_score,
            "assembly_score": asm_score,
            "traceability_score": trace_score,
            "name_score": round(name_score, 1),
        }

    @staticmethod
    def _name_similarity(a: str, b: str) -> float:
        """0-1 keyword overlap ratio between two names."""
        def tokens(s):
            return {w.lower() for w in re.split(r"[\s_\-/]+", s) if w.lower() not in _STOP and len(w) > 1}
        ta, tb = tokens(a), tokens(b)
        if not ta or not tb:
            return 0.0
        return len(ta & tb) / max(len(ta | tb), 1)
