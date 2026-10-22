"""Approval-backed RDF ontology merge service.

Previews are persisted so an operator approves the exact reviewed merge rather
than an arbitrary re-run.  The result is a normal catalog artifact with clear
provenance plus a Semantica version snapshot.
"""
from __future__ import annotations

import json
import hashlib
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rdflib import Graph, Literal, BNode, URIRef, RDF, OWL, RDFS


class GovernedMergeService:
    def __init__(self, catalog: Any, intelligence: Any, root: Path) -> None:
        self.catalog, self.intelligence = catalog, intelligence
        self.path = root / "governed_merge_previews.json"
        self.lock = threading.RLock()
        self.registry = None
        if getattr(catalog, '_postgres_enabled', False):
            from backend.mesh_store import PostgresRegistry
            self.registry = PostgresRegistry('ontology_merge_previews')

    def _operation_lock(self, key='merge-store'):
        return self.registry.advisory_lock(key) if self.registry is not None else self.lock

    def _load(self) -> dict[str, dict[str, Any]]:
        values = json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {}
        if self.registry is not None:
            values.update(self.registry.all())
        return values

    def _save(self, values: dict[str, dict[str, Any]], changed_key: str | None = None) -> None:
        if self.registry is not None:
            selected = {changed_key: values[changed_key]} if changed_key else values
            for key, value in selected.items():
                self.registry.put(key, value)
            return
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(values, indent=2), encoding="utf-8")
        temporary.replace(self.path)

    def preview(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get('background') is True:
            from .merge_background import background_merges
            return background_merges.enqueue(self, payload)
        key = 'preview:' + hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        with self._operation_lock(key) as acquired:
            if acquired is False:
                raise ValueError('A merge operation is already running; refresh and retry')
            from .merge_preparation import prepare
            record = prepare(self, payload)
            values = {} if self.registry is not None else self._load()
            values[record['preview_id']] = record
            self._save(values, record['preview_id'])
            return {key: value for key, value in record.items() if key != 'turtle'}

    def _preview(self, payload: dict[str, Any], *, defer_semantics=False) -> dict[str, Any]:
        supplied = payload.get('source_ontology_ids', [])
        if not isinstance(supplied, list) or not all(isinstance(value, str) and value.strip() for value in supplied):
            raise ValueError('source_ontology_ids must be a list of nonempty ontology IDs')
        source_ids = list(dict.fromkeys(value.strip() for value in supplied))
        if len(source_ids) < 2:
            raise ValueError("At least two distinct source_ontology_ids are required")
        if len(source_ids) > 16:
            raise ValueError('Merge at most 16 ontologies per preview')
        merged, occurrences, sources = Graph(), {}, []
        candidate_graphs = []
        source_metadata = []
        baseline = set()
        for ontology_id in source_ids:
            if self.catalog.get(ontology_id) is not None:
                metadata, content = self.catalog.read_artifact(ontology_id)
            else:
                from .domain.reasoning import OntologyReasoningService
                context = OntologyReasoningService.semantic_context(ontology_id)
                metadata = context['meta']
                path = context['file_path']
                from backend.depo_platform.upload_limits import ontology_upload_limit
                with path.open('rb') as handle:
                    content = handle.read(ontology_upload_limit() + 1)
                if len(content) > ontology_upload_limit():
                    raise ValueError('Merge source exceeds ONTOLOGY_MAX_UPLOAD_BYTES')
                metadata = {**metadata, 'original_filename': path.name}
            parsed = self.catalog._parse_ontology(content, metadata.get('original_filename') or 'ontology.ttl')
            source = Graph()
            source.parse(data=content, format=parsed['rdf_format'])
            candidate_graphs.append(source)
            if metadata.get('status') == 'superseded' or metadata.get('lifecycle_status') in {'deprecated', 'retired'}:
                raise ValueError('Select current, non-retired ontology sources for a merge')
            sources.append({"ontology_id": ontology_id, "ontology_name": metadata["ontology_name"], 'artifact_sha256': hashlib.sha256(content).hexdigest()})
            source_metadata.append(metadata)
            for triple in self._scoped_triples(source):
                key = tuple(term.n3() for term in triple)
                occurrences[key] = occurrences.get(key, 0) + 1
                merged.add(triple)
                if ontology_id == source_ids[-1]:
                    baseline.add(triple)
        mappings = payload.get('entity_mappings', [])
        from .merge_matching import match_entities
        suggestions, matching_report = match_entities(candidate_graphs[0], candidate_graphs[-1])
        if not isinstance(mappings, list) or len(mappings) > 200:
            raise ValueError('entity_mappings must be a list of at most 200 reviewed mappings')
        replacements = {}
        mapping_evidence = []
        from .governance import policy
        governance_rules = policy()
        kinds = {OWL.Class, RDFS.Class, OWL.ObjectProperty, OWL.DatatypeProperty, OWL.AnnotationProperty, OWL.NamedIndividual}
        for item in mappings:
            if not isinstance(item, dict) or not all(isinstance(item.get(key), str) and item[key].startswith(('http://', 'https://', 'urn:')) for key in ('source_iri', 'target_iri')):
                raise ValueError('Each entity mapping requires absolute source_iri and target_iri')
            source, target = URIRef(item['source_iri']), URIRef(item['target_iri'])
            if len(source_ids) != 2 or not any(candidate_graphs[0].triples((source, RDF.type, None))) or not any(candidate_graphs[-1].triples((target, RDF.type, None))):
                raise ValueError('Reviewed mappings must link declared entities from the first source to the second source')
            from backend.depo_platform.ontology_semantics import is_individual
            source_types = set(merged.objects(source, RDF.type)) & kinds
            target_types = set(merged.objects(target, RDF.type)) & kinds
            if is_individual(candidate_graphs[0], source): source_types.add(OWL.NamedIndividual)
            if is_individual(candidate_graphs[-1], target): target_types.add(OWL.NamedIndividual)
            source_types = {OWL.Class if value == RDFS.Class else value for value in source_types}
            target_types = {OWL.Class if value == RDFS.Class else value for value in target_types}
            if source == target or not source_types or source_types != target_types or source in replacements:
                raise ValueError('Entity mappings require distinct declared entities of the same kind and a unique source')
            mapping_evidence.append({'source_iri': str(source), 'target_iri': str(target),
                'individual': OWL.NamedIndividual in source_types,
                'source_context': {predicate: hashlib.sha256(json.dumps(sorted(value.n3() for value in candidate_graphs[0].objects(source, URIRef(predicate)))).encode()).hexdigest()
                                   for predicate in governance_rules['identity_context_predicates'] if any(candidate_graphs[0].objects(source, URIRef(predicate)))},
                'target_context': {predicate: hashlib.sha256(json.dumps(sorted(value.n3() for value in candidate_graphs[-1].objects(target, URIRef(predicate)))).encode()).hexdigest()
                                   for predicate in governance_rules['identity_context_predicates'] if any(candidate_graphs[-1].objects(target, URIRef(predicate)))}})
            replacements[source] = target
        if set(replacements) & set(replacements.values()):
            raise ValueError('Chained or cyclic entity mappings require separate reviewed merges')
        original = set(merged)
        if replacements:
            merged = Graph()
            for triple in original:
                merged.add(tuple(replacements.get(term, term) for term in triple))
        proposed = set(merged)
        added, removed, unchanged = proposed - baseline, baseline - proposed, proposed & baseline
        from heapq import nsmallest
        changes = {'baseline_ontology_id': source_ids[-1], 'added': len(added), 'removed': len(removed),
                   'unchanged': len(unchanged), 'entity_mappings': mappings,
                   'modified_entity_count': len(replacements), 'sample_limit': 200,
                   'added_sample': nsmallest(200, (' '.join(term.n3() for term in triple) for triple in added)),
                   'removed_sample': nsmallest(200, (' '.join(term.n3() for term in triple) for triple in removed)),
                   'unchanged_sample': nsmallest(200, (' '.join(term.n3() for term in triple) for triple in unchanged))}
        from .merge_validation import explicit_conflicts
        conflicts = self._literal_conflicts(merged) + explicit_conflicts(merged)
        from .merge_semantics import validate_merge
        semantic_checks = ({'shacl_conforms': None, 'inferred_conflicts': [], 'owl_rl_performed': False,
                            'status': 'pending'} if defer_semantics else validate_merge(merged, source_metadata, mappings))
        conflicts.extend(semantic_checks['inferred_conflicts'])
        if semantic_checks['shacl_conforms'] is False: conflicts.append({'kind':'shacl_nonconformance','message':'Review the retained SHACL report before approval'})
        from .governance import change_impact
        baseline_entities = {subject for subject, predicate, kind in baseline if predicate == RDF.type and kind in kinds}
        proposed_entities = {subject for subject, predicate, kind in proposed if predicate == RDF.type and kind in kinds}
        removed_active_iris = sorted(str(subject) for subject in baseline_entities - proposed_entities
                                    if not any(str(value).lower() in {'true', '1'} for value in candidate_graphs[-1].objects(subject, OWL.deprecated)))
        preview_id = uuid.uuid4().hex
        record = {"preview_id": preview_id, "created_at": datetime.now(timezone.utc).isoformat(),
                  "source_ontology_ids": source_ids, "sources": sources,
                  "mapping_evidence": mapping_evidence, "governance_policy_sha256": governance_rules["sha256"], "recommended_version_bump": change_impact(added, removed),
                  "removed_active_iris": removed_active_iris,
                  "ontology_name": str(payload.get("ontology_name") or "Merged Ontology"),
                  "prefix": str(payload.get("prefix") or "merged"),
                  "description": str(payload.get("description") or ""),
                  "triple_count": len(merged), "duplicate_triple_count": sum(occurrences.values()) - len(occurrences),
                  "consolidated_triple_count": len(original) - len(merged),
                  "conflicts": conflicts, "publish_recommended": not conflicts and not defer_semantics, "changes": changes,
                  "entity_suggestions": suggestions, "matching_report": matching_report,
                  'semantic_checks': semantic_checks,
                  "validation": {"scope": "RDF union, functional literal conflicts and explicit OWL declaration contradictions",
                      "formal_reasoning_performed": False, 'owl_rl_performed': not defer_semantics,
                      "limitations": ["Different IRIs are not automatically equivalent",
                          "Logical consistency and domain/range compatibility require separate validation"]},
                  "turtle": merged.serialize(format="turtle")}
        values = {} if self.registry is not None else self._load()
        values[preview_id] = record
        self._save(values, preview_id)
        return {key: value for key, value in record.items() if key != "turtle"}

    @staticmethod
    def _entity_suggestions(source_graph, target_graph):
        from backend.ontology_service.merge_matching import match_entities
        return match_entities(source_graph, target_graph)[0]

    def apply(self, preview_id: str, approved_by: str) -> dict[str, Any]:
        with self._operation_lock(preview_id) as acquired:
            if acquired is False:
                raise ValueError('A merge operation is already running; refresh and retry')
            return self._with_source_locks(preview_id, lambda: self._apply(preview_id, approved_by))

    def _with_source_locks(self, preview_id, operation):
        record = self.registry.get(preview_id) if self.registry is not None else self._load().get(preview_id)
        if not record: raise ValueError('Merge preview not found')
        identifiers = sorted(record['source_ontology_ids'])
        def acquire(index):
            if index == len(identifiers): return operation()
            identifier = identifiers[index]
            if self.catalog.get(identifier) is None:
                raise ValueError('Migrate legacy sources to the governed ontology catalog before approving a merge')
            return self.catalog.with_publication_lock(identifier, lambda: acquire(index + 1))
        return acquire(0)

    def _decision_policy(self, record):
        from backend.depo_platform.decision_policy import decision, unavailable_assessment
        try:
            # The owning service evaluates locally; never consume its own HTTP worker pool.
            return self.intelligence.evaluate_decisions('ontology_merge', [decision(
                artifact_sha256=hashlib.sha256(record['turtle'].encode('utf-8')).hexdigest(),
                source_ontology_ids=record['source_ontology_ids'],
                selected_mappings=record.get('changes', {}).get('entity_mappings', []))])
        except Exception as exc:
            return unavailable_assessment('ontology_merge', exc)

    def evaluate_policy(self, preview_id: str) -> dict[str, Any]:
        record = self.registry.get(preview_id) if self.registry is not None else self._load().get(preview_id)
        if not record:
            raise ValueError('Merge preview not found')
        if record.get('background_validation'):
            from .merge_background import background_merges
            if not background_merges.is_complete(record):
                return {'preview_id': preview_id, 'status': 'held', 'policy': 'conflict-free-union-v1',
                        'reasons': ['semantic_validation_incomplete'], 'conflicts': record.get('conflicts', [])}
        from .merge_semantics import validate_merge
        conflicts = validate_merge(record['turtle'], [], declarations_only=True)['inferred_conflicts']
        # Automatic union preserves every entity identity. Consolidations remain
        # explicit reviewed operations because RDF union cannot prove equivalence.
        from .governance import audit_ontology_bounded as audit_ontology
        governance = audit_ontology(record)
        shared = self._decision_policy(record)
        governance['decision_policy'] = shared
        reasons = []
        if shared['blocking']: reasons.append('decision_policy_' + shared['status'])
        if governance['overall_verdict'] != 'APPROVED': reasons.append('steward_governance_hold')
        if conflicts or record.get('conflicts'): reasons.append('unresolved_rdf_owl_conflicts')
        if record.get('changes', {}).get('entity_mappings'): reasons.append('entity_consolidation_requires_review')
        return {'preview_id': preview_id, 'policy': 'conflict-free-union-v1',
                'status': 'held' if reasons else 'ready', 'reasons': reasons,
                'conflicts': conflicts, 'changes': record.get('changes'),
                'validation': record.get('validation'), 'governance': governance}

    def receipt(self, preview_id: str) -> dict[str, Any]:
        record = self.registry.get(preview_id) if self.registry is not None else self._load().get(preview_id)
        if not record or not record.get('applied_result'):
            raise ValueError('No completed merge receipt is retained')
        result = record['applied_result']
        artifact, content = self.catalog.read_artifact(result['ontology']['ontology_id'])
        provenance = artifact.get('provenance') or {}
        if (result.get('preview_id') != preview_id or provenance.get('preview_id') != preview_id
                or provenance.get('source_ontology_ids') != record['source_ontology_ids']
                or hashlib.sha256(content).digest() != hashlib.sha256(record['turtle'].encode('utf-8')).digest()):
            raise ValueError('Merge receipt does not match the retained artifact')
        return result

    def apply_automatic(self, preview_id: str, approved_by: str) -> dict[str, Any]:
        with self._operation_lock(preview_id) as acquired:
            if acquired is False:
                raise ValueError('A merge operation is already running; refresh and retry')
            record = self.registry.get(preview_id) if self.registry is not None else self._load().get(preview_id)
            if record and record.get('applied_result'):
                return {**self.receipt(preview_id), 'approval_policy': record.get('approval_policy')}
            decision = self.evaluate_policy(preview_id)
            if decision['status'] == 'held':
                return decision
            return {**self._with_source_locks(preview_id, lambda: self._apply(preview_id, approved_by, approval_policy=decision)), 'approval_policy': decision}

    def _apply(self, preview_id: str, approved_by: str, approval_policy=None) -> dict[str, Any]:
        if not str(approved_by).strip():
            raise ValueError("approved_by is required for a governed merge")
        if self.registry is not None:
            retained = self.registry.get(preview_id)
            values = {preview_id: retained} if retained else self._load()
        else:
            values = self._load()
        record = values.get(preview_id)
        if not record:
            raise ValueError("Merge preview not found")
        if record["conflicts"]:
            raise ValueError("Merge preview contains unresolved RDF/OWL conflicts")
        if record.get('applied_result'):
            return record['applied_result']
        if record.get('background_validation'):
            from .merge_background import background_merges
            if not background_merges.is_complete(record):
                raise ValueError('Semantic validation has not completed for this reviewed merge')
        source_metadata = []
        for source in record.get('sources', []):
            ontology_id = source['ontology_id']
            if self.catalog.get(ontology_id) is not None:
                metadata, content = self.catalog.read_artifact(ontology_id)
            else:
                from .domain.reasoning import OntologyReasoningService
                from backend.depo_platform.upload_limits import ontology_upload_limit
                context = OntologyReasoningService.semantic_context(ontology_id)
                metadata = context['meta']
                with context['file_path'].open('rb') as stream:
                    content = stream.read(ontology_upload_limit() + 1)
                if len(content) > ontology_upload_limit(): raise ValueError('Merge source exceeds upload limit')
            if not source.get('artifact_sha256') or hashlib.sha256(content).hexdigest() != source['artifact_sha256'] or metadata.get('status') == 'superseded' or metadata.get('lifecycle_status') in {'deprecated', 'retired'}:
                raise ValueError('A merge source changed or became inactive. Generate and review a new preview')
            source_metadata.append(metadata)
        if not record.get('sources'):
            raise ValueError('Merge preview lacks verified sources; generate a new preview')
        from .merge_semantics import validate_merge
        if record.get('background_validation'):
            from .merge_semantics import validation_fingerprint
            receipt = record.get('validation_receipt', {})
            if receipt.get('graph_sha256') != hashlib.sha256(record['turtle'].encode('utf-8')).hexdigest() or receipt.get('policy_sha256') != validation_fingerprint(source_metadata):
                raise ValueError('Reviewed graph or validation policy/shapes changed; generate a new preview')
            semantic_checks = record['semantic_checks']
        else:
            semantic_checks = validate_merge(record['turtle'], source_metadata, record.get('changes', {}).get('entity_mappings', []))
        if semantic_checks['shape_digests'] != (record.get('semantic_checks') or {}).get('shape_digests'):
            raise ValueError('Merge validation shapes changed; generate and review a new preview')
        if not semantic_checks['shacl_conforms'] or semantic_checks['inferred_conflicts']:
            raise ValueError('Reviewed merge no longer passes SHACL/OWL-RL checks; create a new preview')
        from .governance import audit_ontology_bounded as audit_ontology
        governance = audit_ontology({**record, 'semantic_checks': semantic_checks})
        if governance['overall_verdict'] != 'APPROVED':
            raise ValueError('Ontology Steward policy blocks this merge; evaluate the saved plan and review its quarantined findings')
        shared = self._decision_policy(record)
        governance['decision_policy'] = shared
        if shared['blocking']:
            record['decision_policy'] = shared
            self._save(values, preview_id)
            raise ValueError('Semantica decision policy holds this merge; review the retained assessment')
        record['governance_audit'] = governance
        if not record.get('approved_by'):
            record['approved_by'] = approved_by
            if approval_policy is not None:
                record['approval_policy'] = approval_policy
            self._save(values, preview_id)
        approved_by = record['approved_by']
        artifact = self.catalog.register(
            content=record["turtle"].encode("utf-8"), filename=f"{record['prefix']}_merged.ttl",
            ontology_name=record["ontology_name"], prefix=record["prefix"], description=record["description"],
            source='governed-merge:' + hashlib.sha256(preview_id.encode('utf-8')).hexdigest(), extra_metadata={"status": "merged", "provenance": {"preview_id": preview_id,
            "source_ontology_ids": record["source_ontology_ids"], "approved_by": approved_by, "governance_audit": governance,
            **({'approval_policy': record['approval_policy']} if record.get('approval_policy') else {})}},
        )
        version = self.intelligence.create_merge_version(ontology={"ontology_id": artifact["ontology_id"], "provenance": artifact["provenance"], "triple_count": record["triple_count"]}, author=approved_by)
        result = {"status": "merged", "ontology": artifact, "version": version, "preview_id": preview_id,
                  "changes": record.get('changes'), "approved_by": approved_by, "governance": governance}
        record['applied_result'] = result
        self._save(values, preview_id)
        return result

    @staticmethod
    def _scoped_triples(graph):
        """Blank nodes have document scope; never join them across source files."""
        mapping = {}
        for triple in graph:
            yield tuple(mapping.setdefault(term, BNode()) if isinstance(term, BNode) else term for term in triple)

    @staticmethod
    def _literal_conflicts(graph: Graph) -> list[dict[str, str]]:
        from rdflib.namespace import RDF, OWL
        functional = set(graph.subjects(RDF.type, OWL.FunctionalProperty))
        values: dict[tuple[str, str], set[str]] = {}
        for subject, predicate, obj in graph:
            # RDF properties are multivalued unless declared functional.
            # Distinct labels/comments (including translations) are not conflicts.
            if predicate in functional and isinstance(obj, Literal):
                values.setdefault((str(subject), str(predicate)), set()).add(obj.n3())
        return [{"subject": subject, "predicate": predicate, "values": sorted(items)}
                for (subject, predicate), items in values.items() if len(items) > 1]
