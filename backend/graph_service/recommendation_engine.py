"""Shared bounded recommendation analysis for service and compatibility callers."""
import time
import logging
from fastapi import HTTPException
from neo4j.exceptions import DriverError, Neo4jError
from .engineering_comparison import compare, declared_relation, kind, local, name_score, values
from backend.depo_platform.graph_access import graph_projection_reader

EXCLUDED = ['StagedOntologyResource', 'RetainedOntologyIdentity', 'OntologyPublication',
            'GraphChunk', 'DatasheetChunk', 'OntologyClass', 'ObjectProperty', 'DatatypeProperty', 'AnnotationProperty']
IMPACT = {'impacts', 'affects', 'cmhasimpacteditem', 'cmhasproblemitem', 'cmhassolutionitem',
          'hasimpacteditem', 'hasproblemitem', 'hassolutionitem'}
TRACE = {'satisfies', 'seg0satisfy', 'fndtracelink', 'tracelink', 'realizes', 'tracesto', 'traceto', 'allocatedto'}
BOM = {'haschildinstance', 'haschild', 'contains', 'haspart', 'partof', 'childof', 'parentof', 'usedby', 'dependson'}
PROCESS = {'manufacturedby', 'processedby', 'produces', 'consumes', 'uses', 'performs', 'processes'}
REFERENCE = {'relatedrefs', 'relatedref', 'masterref', 'masterreference', 'partref', 'productref', 'revisionref', 'instancedref'}


def display(record):
    props = record.get('properties') or {}
    return str(props.get('name') or props.get('label') or props.get('title') or record.get('name') or 'Unnamed business record')[:250]


def provenance(record):
    props = record.get('properties') or {}
    return {'node_id': record['id'], **{key:props[key] for key in
            ('ontology_id','source_ontology','import_id','publication_revision','source_revision','artifact_digest','updated_at')
            if isinstance(props.get(key),(str,int,float)) and not isinstance(props.get(key),bool)}}


class RecommendationEngine:
    def __init__(self, publisher):
        self.publisher = publisher
        self.deadline = time.monotonic() + 20

    def query(self, query, **params):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise HTTPException(503, 'Recommendation analysis exceeded its time budget; narrow the selected scope')
        try:
            return self.publisher._session_rows(query, _timeout_seconds=remaining, **params)
        except (DriverError, Neo4jError, OSError, RuntimeError) as exc:
            logging.getLogger(__name__).exception('Engineering recommendation graph read failed')
            raise HTTPException(503, 'Engineering graph evidence is unavailable; check service readiness and retry') from exc

    @staticmethod
    def scope(scope):
        if scope is not None and not isinstance(scope, dict):
            raise HTTPException(422, 'Recommendation scope must identify one ontology or prefix')
        scope = scope or {}
        if set(scope) - {'ontology_id','ontology_prefix','prefix','node_id','element_id'}:
            raise HTTPException(422, 'Use ontology_id or ontology_prefix for recommendation scope')
        if any(not isinstance(value,str) or len(value)>256 for value in scope.values()):
            raise HTTPException(422, 'Invalid recommendation scope or identity')
        return {'scope': scope.get('ontology_id', ''), 'prefix': scope.get('ontology_prefix') or scope.get('prefix', '')}

    def record(self, node_id, scope):
        rows = self.query(
            '/* recommendation-record */ MATCH (n) WHERE elementId(n)=$id '
            'AND none(label IN labels(n) WHERE label IN $excluded) '
            "AND ($scope='' OR n.ontology_id=$scope OR n.source_ontology=$scope) "
            "AND ($prefix='' OR n.prefix=$prefix OR n.ontology_prefix=$prefix) "
            'OPTIONAL MATCH (n)-[typing:INSTANCE_OF|TYPED_BY|SEMANTICALLY_MAPPED_TO]->(cls) '
            'WHERE NOT cls:StagedOntologyResource AND NOT cls:RetainedOntologyIdentity '
            'RETURN elementId(n) AS id, labels(n) AS labels, properties(n) AS properties, '
            'collect(DISTINCT coalesce(cls.iri,cls.name,cls.label)) AS mapped_types LIMIT 1',
            id=node_id, excluded=EXCLUDED, **self.scope(scope))
        if not rows:
            raise HTTPException(404, 'Selected business record is unavailable in this scope')
        return rows[0]

    def candidate_records(self, root, scope):
        # Typed retrieval admits differently named parts; lexical search alone
        # cannot discover a reuse candidate whose engineering name differs.
        types = [value for value in (root.get('properties') or {}).get('rdf_types', [])
                 if value != 'http://www.w3.org/2002/07/owl#NamedIndividual']
        roles = ['part', 'product', 'productrevision', 'productinstance', 'component', 'item', 'itemrevision', 'assembly']
        rows = self.query(
            '/* recommendation-candidates */ MATCH (n) WHERE elementId(n)<>$id '
            'AND none(label IN labels(n) WHERE label IN $excluded) '
            "AND ($scope='' OR n.ontology_id=$scope OR n.source_ontology=$scope) "
            "AND ($prefix='' OR n.prefix=$prefix OR n.ontology_prefix=$prefix) "
            'AND (any(t IN coalesce(n.rdf_types,[]) WHERE t IN $types) '
            "OR any(t IN coalesce(n.rdf_types,[]) WHERE toLower(last(split(last(split(t,'#')),'/'))) IN $roles) "
            'OR any(label IN labels(n) WHERE toLower(label) IN $roles) '
            "OR toLower(coalesce(n.semantic_role,n.element_type,'')) IN $roles "
            'OR EXISTS { MATCH (n)-[:INSTANCE_OF|TYPED_BY|SEMANTICALLY_MAPPED_TO]->(cls) '
            'WHERE coalesce(cls.iri,cls.name,cls.label) IN $mapped_types }) '
            'WITH n ORDER BY elementId(n) LIMIT 201 '
            'OPTIONAL MATCH (n)-[:INSTANCE_OF|TYPED_BY|SEMANTICALLY_MAPPED_TO]->(cls) '
            'WHERE NOT cls:StagedOntologyResource AND NOT cls:RetainedOntologyIdentity '
            'RETURN elementId(n) AS id, labels(n) AS labels, properties(n) AS properties, '
            'collect(DISTINCT coalesce(cls.iri,cls.name,cls.label)) AS mapped_types ORDER BY id', id=root['id'], excluded=EXCLUDED, types=types,
            roles=roles, mapped_types=root.get('mapped_types', []), **self.scope(scope))
        return rows[:200], len(rows) > 200

    @graph_projection_reader
    def similar(self, root_id, scope=None, top_n=10):
        root = self.record(root_id, scope)
        if kind(root) not in {'part', 'assembly'}:
            raise HTTPException(422, 'Select a part or assembly with a declared business type or ontology mapping')
        rows, limited = self.candidate_records(root, scope)
        candidates, excluded = [], 0
        for row in rows:
            if kind(row) != kind(root):
                excluded += 1
                continue
            comparisons = compare(root.get('properties'), row.get('properties'))
            checked = [entry for entry in comparisons if entry['status'] != 'unassessed']
            matched = sum(entry['status'] == 'match' for entry in checked)
            conflicts = [entry['property'] for entry in checked if entry['status'] == 'conflict']
            lexical = name_score(display(root), display(row))
            # Missing engineering evidence earns no points; lexical agreement
            # cannot mask a dimensional/material/configuration conflict.
            name_factor = .5 * lexical['token_jaccard'] + .5 * lexical['character_trigram_jaccard']
            score = 15 + 20 * name_factor + 65 * matched / len(comparisons)
            if conflicts:
                score = min(score, 35)
            candidates.append({'node_id': row['id'], 'name': display(row),
                'source_evidence': provenance(row),
                'source_tag': (row.get('properties') or {}).get('ontology_id'), 'type_match': True,
                'source_tag_match': (row.get('properties') or {}).get('ontology_id') == (root.get('properties') or {}).get('ontology_id'),
                'similarity_score': round(score, 2), 'score_evidence': {**lexical, 'graph_type_match': True,
                    'engineering_matches': matched, 'engineering_assessed': len(checked),
                    'weights': {'business_type': .15, 'name': .20, 'engineering_properties': .65}},
                'engineering_comparisons': comparisons, 'conflicts': conflicts,
                'evidence_coverage': round(len(checked) / len(comparisons), 3),
                'compatibility': 'conflicting_evidence' if conflicts else 'requires_engineering_review',
                'eligible_for_substitution': False,
                'missing_evidence': [entry['property'] for entry in comparisons if entry['status'] == 'unassessed'],
                'shared_assembly': None, 'traceability_link': None, 'rflp_layer_match': None,
                'comparison_basis': 'Declared business type, name tokens/trigrams and engineering properties with explicit units. Engineering release approval is required for substitution.'})
        candidates.sort(key=lambda row: (bool(row['conflicts']), -row['similarity_score'], row['node_id']))
        return {'source_part': {'node_id': root['id'], 'name': display(root), 'source_tag': (root.get('properties') or {}).get('ontology_id')},
            'source_evidence': provenance(root),
            'similar_parts': candidates[:max(1, min(top_n, 50))], 'advisory_only': True,
            'coverage': {'candidate_limit': 200, 'candidates_examined': len(rows), 'category_mismatches_excluded': excluded,
                         'limit_reached': limited, 'whole_graph_complete': False},
            'ranking_scope': 'Up to 200 typed engineering candidates. Scores combine type (15%), tokens/trigrams (20%) and declared engineering properties (65%). Missing evidence earns no engineering points; conflicts hold reuse. Scores are not calibrated confidence.'}

    def edges(self, frontier, scope):
        # Select eligible dependency edges BEFORE the cap so unrelated metadata
        # does not crowd impact evidence out of the retained neighborhood.
        return self.query(
            '/* recommendation-dependencies */ UNWIND $frontier AS id '
            'MATCH (a) WHERE elementId(a)=id MATCH (a)-[r]-(b) '
            'WHERE none(label IN labels(b) WHERE label IN $excluded) '
            "AND ($scope='' OR b.ontology_id=$scope OR b.source_ontology=$scope) "
            "AND ($prefix='' OR b.prefix=$prefix OR b.ontology_prefix=$prefix) "
            "WITH a,b,r,toLower(replace(replace(last(split(last(split(coalesce(r.predicate,type(r)),'#')),'/')),'_',''),'-','')) AS relation "
            'WHERE relation IN $relations AND (NOT relation IN $reference_relations '
            'OR any(label IN labels(a)+labels(b) WHERE toLower(label) IN $carrier_types) '
            "OR any(t IN coalesce(a.rdf_types,[])+coalesce(b.rdf_types,[]) WHERE toLower(last(split(last(split(t,'#')),'/'))) IN $carrier_types)) "
            'WITH a,b,r ORDER BY elementId(a),elementId(r) LIMIT 601 '
            'OPTIONAL MATCH (b)-[:INSTANCE_OF|TYPED_BY|SEMANTICALLY_MAPPED_TO]->(cls) '
            'WHERE NOT cls:StagedOntologyResource AND NOT cls:RetainedOntologyIdentity '
            'RETURN elementId(a) AS from_id, elementId(b) AS to_id, labels(b) AS labels, properties(b) AS properties, '
            'elementId(r) AS relationship_id, type(r) AS relationship_type, r.predicate AS predicate, '
            'elementId(startNode(r)) AS start_id, elementId(endNode(r)) AS end_id, '
            'collect(DISTINCT coalesce(cls.iri,cls.name,cls.label)) AS mapped_types '
            'ORDER BY from_id, relationship_id', frontier=frontier, excluded=EXCLUDED,
            relations=sorted(IMPACT | TRACE | BOM | PROCESS | REFERENCE), reference_relations=sorted(REFERENCE),
            carrier_types=['generalrelation','relationshipcarrier'], **self.scope(scope))

    @graph_projection_reader
    def impact(self, root_id, scope=None):
        root = self.record(root_id, scope)
        root_kind = kind(root)
        if root_kind not in {'part', 'assembly', 'change'}:
            raise HTTPException(422, 'Select a typed change, part or assembly to assess dependency impact')
        records, paths, path_names = {root_id: root}, {root_id: []}, {root_id: [display(root)]}
        frontier, results, limited, examined = [root_id], {}, False, 0
        # Four physical hops permit a two-hop relation carrier followed by
        # assembly/process propagation. No unbounded variable-length expansion.
        for depth in range(1, 5):
            if not frontier:
                break
            rows = self.edges(frontier, scope)
            limited |= len(rows) > 600
            next_frontier = []
            for edge in rows[:600]:
                examined += 1
                source = edge['from_id']
                target = edge['to_id']
                if target in paths or source not in paths:
                    continue
                if len(records) >= 200:
                    limited = True
                    break
                record = {'id': target, 'labels': edge.get('labels', []), 'properties': edge.get('properties', {}), 'mapped_types': edge.get('mapped_types', [])}
                category = kind(record)
                relation = local(edge.get('predicate') or edge.get('relationship_type'))
                source_kind = kind(records[source])
                # GeneralRelation must carry an explicit change-impact type;
                # arbitrary reference records never become impact paths.
                carrier_type = declared_relation(record['properties'])
                source_carrier_type = declared_relation(records[source]['properties'])
                carrier_edge = relation in REFERENCE and ((category == 'carrier' and source_kind == 'change' and bool(carrier_type & IMPACT))
                                  or (source_kind == 'carrier' and bool(source_carrier_type & IMPACT)))
                if relation in REFERENCE and not carrier_edge:
                    continue
                if category == 'carrier' and not carrier_edge:
                    continue
                if category not in {'part', 'assembly', 'process', 'requirement', 'carrier'}:
                    continue
                # Impact predicates point from the change to affected records.
                # BOM parent->child is traversed upward for change propagation.
                if relation in IMPACT and edge['start_id'] != source:
                    continue
                if relation in {'haschildinstance', 'haschild', 'contains', 'haspart', 'parentof'} and edge['end_id'] != source:
                    continue
                if relation in {'partof', 'childof', 'usedby'} and edge['start_id'] != source:
                    continue
                if relation == 'dependson' and edge['end_id'] != source:
                    continue
                classification = 'declared_business_type'
                if category == 'part' and relation in {'haschildinstance','haschild','contains','haspart','parentof','partof','childof','usedby'}:
                    category, classification = 'assembly', 'recorded_parent_relationship'
                path = [*paths[source], {key: edge.get(key) for key in ('relationship_id','relationship_type','predicate','start_id','end_id')}]
                paths[target], records[target] = path, record
                path_names[target] = [*path_names[source], display(record)]
                next_frontier.append(target)
                if category == 'carrier':
                    continue
                # Revision/configuration differences are exposed, not silently
                # treated as active effectivity or automatically excluded.
                comparisons = compare(root['properties'], record['properties'])
                constraints = [entry for entry in comparisons if entry['property'] in {'revision','configuration','effectivity'}]
                results[target] = {'node_id': target, 'name': display(record), 'category': category, 'depth': depth,
                    'source_evidence': provenance(record),
                    'classification_basis': classification,
                    'source_tag': record['properties'].get('ontology_id'), 'relation_type': relation,
                    'relationship_id': edge.get('relationship_id'), 'path': path,
                    'path_names': path_names[target],
                    'from_part': display(root), 'linked_part': display(root),
                    'assembly_name': display(record), 'link_type': relation,
                    'configuration_review': constraints, 'effectivity_verified': False,
                    'conflicts': [item['property'] for item in constraints if item['status'] == 'conflict'],
                    'review_status': 'configuration_conflict' if any(item['status'] == 'conflict' for item in constraints) else 'effectivity_review_required',
                    'engineering_review_required': True,
                    'evidence_kind': 'explicit_impact' if relation in IMPACT or carrier_edge else 'dependency_candidate'}
                if len(records) >= 200:
                    limited = True
                    break
            frontier = sorted(set(next_frontier))
            if limited:
                break
        entries = sorted(results.values(), key=lambda row: (row['depth'], row['node_id']))
        return {'change_entity': {'node_id': root_id, 'name': display(root), 'source_tag': root['properties'].get('ontology_id'),
                                 'revision': (values(root['properties']).get('revision') or [None])[0]},
            'source_evidence': provenance(root),
            'impacted_parts': [row for row in entries if row['category'] == 'part'],
            'assembly_impact': [row for row in entries if row['category'] == 'assembly'],
            'impacted_requirements': [row for row in entries if row['category'] == 'requirement'],
            'process_impacts': [row for row in entries if row['category'] == 'process'],
            'realization_chain': entries, 'impact_score': None,
            'evidence_status': 'linked_candidates' if entries else 'insufficient',
            'message': 'Review the retained dependency paths and configuration/effectivity before authorizing a change.' if entries else 'Impact is unknown: no eligible dependency paths were found within the selected scope and traversal budget.',
            'coverage': {'depth': 4, 'node_limit': 200, 'relationships_examined': examined,
                         'limit_reached': limited, 'whole_graph_complete': False},
            'traceability': 'Bounded four-hop dependency analysis, including explicit impact carriers, upward assembly links, traceability and process dependencies. Paths retain relationship identity and direction. Configuration/effectivity and impact severity require review.'}
