"""Similar Parts Recommender Service.

Given a part name, finds similar parts using weighted multi-factor scoring:
- sourceTag match      (20 pts) — same entity type
- rflpLayer match      (15 pts) — same RFLP layer
- Assembly co-occurrence (30 pts) — same PLMXMLFile or sibling ProductInstances
- Traceability link    (20 pts) — connected via tracesTo / realizes / linkedTo
- Name similarity      (15 pts) — shared keywords in name
"""

import logging
import os
import re
from difflib import SequenceMatcher

from .recommendation_semantics import pick_semantic_source
from .recommendation_scope import cypher_scope_filter

logger = logging.getLogger(__name__)

def _is_business_name(value: str) -> bool:
    text = str(value or '').strip()
    if not text:
        return False
    return re.match(r'^id[\w:-]*$', text, flags=re.IGNORECASE) is None

# Stop-words stripped from names before keyword comparison
_STOP = frozenset({"the", "a", "an", "of", "for", "and", "in", "to", "with", "on", "at", "by", "is", "rev", "revision"})


class SimilarPartsRecommender:
    """Find parts similar to a given part using graph structure + properties."""

    def __init__(self, graph):
        self._graph = graph

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def recommend(self, part_name: str, top_n: int = 10, scope: dict | None = None, node_id: str | None = None) -> dict:
        """Return the top-N most similar parts to *part_name*."""
        source = self._find_source_part_by_id(str(node_id), scope=scope) if node_id else None
        if not source:
            source = self._find_source_part(part_name, scope=scope)
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
            cand = candidates.setdefault(t["eid"], {**t, "assembly": False, "trace_link": t.get("link_type"), "semantic_similarity": 0.0})
            cand["trace_link"] = t.get("link_type")

        # Factor 4: semantic candidates from graph embeddings when available
        semantic = []
        if isinstance(scope, dict) and scope.get('use_embeddings'):
            semantic = self._find_semantic_candidates(source, part_name, top_n=max(top_n * 3, 15))
        for s in semantic:
            cand = candidates.setdefault(s["eid"], {**s, "assembly": False, "trace_link": None, "semantic_similarity": 0.0})
            cand["semantic_similarity"] = max(float(cand.get("semantic_similarity") or 0.0), float(s.get("semantic_similarity") or 0.0))
            if not cand.get("name") and s.get("name"):
                cand["name"] = s.get("name")
            if not cand.get("source_tag") and s.get("source_tag"):
                cand["source_tag"] = s.get("source_tag")
            if not cand.get("rflp_layer") and s.get("rflp_layer"):
                cand["rflp_layer"] = s.get("rflp_layer")

        if not candidates:
            lexical = self._find_lexical_candidates(source, part_name, top_n=max(top_n * 3, 20))
            for s in lexical:
                candidates.setdefault(s['eid'], {**s, 'assembly': False, 'trace_link': None, 'semantic_similarity': 0.0})

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
                "semantic_similarity": round(float(info.get("semantic_similarity") or 0.0) * 100, 1),
                "score_breakdown": score_detail,
            })

        scored.sort(key=lambda x: x["similarity_score"], reverse=True)
        deduped = []
        seen_names = set()
        for item in scored:
            norm_name = str(item.get('name') or '').strip().lower()
            if not norm_name or norm_name in seen_names:
                continue
            seen_names.add(norm_name)
            deduped.append(item)
            if len(deduped) >= top_n:
                break
        return {
            "source_part": {
                "name": source["name"],
                "source_tag": source.get("source_tag"),
                "rflp_layer": source.get("rflp_layer"),
            },
            "similar_parts": deduped,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _find_source_part_by_id(self, node_id: str, scope: dict | None = None) -> dict | None:
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
                   cls.name AS rflp_layer, elementId(p) AS eid,
                   cls.name AS class_name, labels(p) AS labels,
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
            "rflp_layer": row.get("rflp_layer"),
            "eid": row.get("eid"),
            "class_name": row.get("class_name"),
        }

    def _find_source_part(self, name: str, scope: dict | None = None) -> dict | None:
        scope_clause, scope_params = cypher_scope_filter("p", scope)
        rows = self._graph.query(
            """
            MATCH (p)
            WHERE toLower(p.name) CONTAINS toLower($name)
            """ + scope_clause + """
            OPTIONAL MATCH (p)-[:INSTANCE_OF]->(cls:OntologyClass)
            RETURN p.name AS name, coalesce(cls.name, head(labels(p))) AS source_tag,
                   cls.name AS rflp_layer, elementId(p) AS eid,
                   cls.name AS class_name, labels(p) AS labels,
                   p.element_type AS element_type
            LIMIT 25
            """,
            params={"name": name, **scope_params},
        )
        if not rows:
            return None
        best = pick_semantic_source(name, rows, prefer="part")
        return best

    def _find_assembly_siblings(self, source: dict) -> list[dict]:
        """Individuals sharing a PLMXMLFile with the source."""
        rows = self._graph.query(
            """
            MATCH (src) WHERE elementId(src) = $eid
            MATCH (src)-[:MASTER_REF|MASTERREF|PART_REF|PARTREF|PRODUCT_REF|REVISIONREF|INSTANCEDREF]-(hub)-[:MASTER_REF|MASTERREF|PART_REF|PARTREF|PRODUCT_REF|REVISIONREF|INSTANCEDREF]-(sib)
            WHERE sib <> src AND sib.name IS NOT NULL
            OPTIONAL MATCH (sib)-[:INSTANCE_OF]->(cls:OntologyClass)
            RETURN DISTINCT sib.name AS name, coalesce(cls.name, head(labels(sib))) AS source_tag,
                   cls.name AS rflp_layer, elementId(sib) AS eid,
                   cls.name AS class_name
            """,
            params={"eid": source["eid"]},
        )
        return [row for row in rows if _is_business_name(row.get('name'))]

    def _find_semantic_candidates(self, source: dict, query_text: str, top_n: int = 20) -> list[dict]:
        """Find semantically similar business objects using graph embeddings when available."""
        try:
            try:
                from ..core.llm import embeddings, EMBEDDER_AVAILABLE
            except Exception:
                from core.llm import embeddings, EMBEDDER_AVAILABLE

            if not EMBEDDER_AVAILABLE:
                return []

            vector_index_name = os.getenv('NEO4J_GRAPH_VECTOR_INDEX', 'graph_embedding')
            candidate_limit = max(top_n * 3, 20)
            query_embedding = embeddings.embed_query(query_text or source.get('name') or '')
            rows = self._graph.query(
                """
                CALL db.index.vector.queryNodes($index_name, $candidate_limit, $embedding)
                YIELD node, score
                MATCH (node)-[:EMBEDDED_FROM]->(src)
                WHERE elementId(src) <> $eid
                  AND NOT (src:DatasheetChunk OR src:GraphChunk)
                  AND coalesce(src.name, '') <> ''
                OPTIONAL MATCH (src)-[:INSTANCE_OF]->(cls:OntologyClass)
                WITH src, cls, max(score) AS semantic_similarity
                RETURN DISTINCT
                  elementId(src) AS eid,
                  src.name AS name,
                  coalesce(cls.name, head(labels(src))) AS source_tag,
                  cls.name AS rflp_layer,
                  cls.name AS class_name,
                  semantic_similarity
                ORDER BY semantic_similarity DESC
                LIMIT $candidate_limit
                """,
                params={
                    'index_name': vector_index_name,
                    'candidate_limit': candidate_limit,
                    'embedding': query_embedding,
                    'eid': source.get('eid'),
                },
            ) or []
        except Exception as exc:
            logger.info('Semantic similarity candidates unavailable, using structural scoring only: %s', exc)
            return []

        results = []
        seen = set()
        for row in rows:
            eid = row.get('eid')
            if not eid or eid in seen:
                continue
            seen.add(eid)
            results.append({
                'eid': eid,
                'name': row.get('name'),
                'source_tag': row.get('source_tag'),
                'rflp_layer': row.get('rflp_layer'),
                'class_name': row.get('class_name'),
                'semantic_similarity': float(row.get('semantic_similarity') or 0.0),
            })
            if len(results) >= top_n:
                break
        return results

    def _find_lexical_candidates(self, source: dict, query_text: str, top_n: int = 20) -> list[dict]:
        rows = self._graph.query(
            """
            MATCH (cand)
            WHERE elementId(cand) <> $eid
              AND coalesce(cand.name, '') <> ''
              AND toLower(coalesce(cand.name, '')) CONTAINS toLower($query)
            OPTIONAL MATCH (cand)-[:INSTANCE_OF]->(cls:OntologyClass)
            RETURN DISTINCT
              elementId(cand) AS eid,
              coalesce(cand.name, '') AS name,
              coalesce(cls.name, head(labels(cand))) AS source_tag,
              cls.name AS rflp_layer,
              cls.name AS class_name
            LIMIT $limit
            """,
            params={'eid': source.get('eid'), 'query': query_text or source.get('name') or '', 'limit': top_n},
        ) or []
        return [row for row in rows if _is_business_name(row.get('name'))]

    def _find_traceability_connections(self, source: dict) -> list[dict]:
        """Parts connected via tracesTo, realizes, linkedTo, allocates."""
        rows = self._graph.query(
            """
            MATCH (src) WHERE elementId(src) = $eid
            MATCH (src)-[r:FND_TRACELINK|RELATEDREFS|SEG0SATISFY]-(conn)
            WHERE conn <> src AND conn.name IS NOT NULL
              AND NOT conn:GeneralRelation
            OPTIONAL MATCH (conn)-[:INSTANCE_OF]->(cls:OntologyClass)
            RETURN DISTINCT conn.name AS name, coalesce(cls.name, head(labels(conn))) AS source_tag,
                   cls.name AS rflp_layer, type(r) AS link_type,
                   elementId(conn) AS eid, cls.name AS class_name
            """,
            params={"eid": source["eid"]},
        )
        return [row for row in rows if _is_business_name(row.get('name'))]

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

        # Semantic similarity from graph embeddings (0-20 pts)
        semantic_similarity = max(0.0, min(float(candidate.get("semantic_similarity") or 0.0), 1.0))
        semantic_score = semantic_similarity * 20.0

        # Name similarity (15 pts)
        name_score = self._name_similarity(source.get("name", ""), candidate.get("name", "")) * 15.0

        total = st_score + rl_score + asm_score + trace_score + semantic_score + name_score
        return {
            "total": min(total, 100.0),
            "source_tag_match": st_match,
            "source_tag_score": st_score,
            "rflp_layer_match": rl_match,
            "rflp_layer_score": rl_score,
            "assembly_score": asm_score,
            "traceability_score": trace_score,
            "semantic_score": round(semantic_score, 1),
            "semantic_similarity": round(semantic_similarity * 100, 1),
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
