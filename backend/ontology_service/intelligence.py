"""Semantica quality and evolution capabilities exposed as explicit APIs."""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
import json
import os
import re
import hashlib
import math
from pathlib import Path
from typing import Any

from semantica.change_management import OntologyVersionManager
from semantica.conflicts import detect_conflicts, resolve_conflicts
from semantica.deduplication import detect_duplicates, merge_entities
from semantica.kg import GraphAnalyzer
from semantica.context import ContextGraph
from backend.mesh_store import PostgresRegistry


def serialise(value: Any) -> Any:
    if is_dataclass(value):
        return {key: serialise(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): serialise(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [serialise(item) for item in value]
    if hasattr(value, "__dict__"):
        return serialise(vars(value))
    if hasattr(value, "value"):
        return value.value
    return value


class SemanticIntelligence:
    def __init__(self, root: Path | None, registry: Any | None = None) -> None:
        if root is not None:
            root.mkdir(parents=True, exist_ok=True)
        self.root = root
        self.registry = registry or PostgresRegistry("ontology_semantic_policies")
        self.legacy_policy_path = root / "semantica_policies.json" if root is not None else None

    def _policies(self) -> list[dict[str, Any]]:
        value = self.registry.get("policies")
        if isinstance(value, dict) and isinstance(value.get("items"), list):
            for policy in value["items"]:
                if isinstance(policy, dict) and policy.get("policy_id"):
                    self.registry.put(f"policy:{policy['policy_id']}", policy)
            self.registry.put("policies", {"migrated": True})
            value = {"migrated": True}
        if value is None and self.legacy_policy_path is not None and self.legacy_policy_path.is_file():
            try:
                items = json.loads(self.legacy_policy_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise RuntimeError(f"Legacy Semantica policies are unreadable: {exc}") from exc
            for policy in items if isinstance(items, list) else []:
                if isinstance(policy, dict) and policy.get("policy_id"):
                    self.registry.put(f"policy:{policy['policy_id']}", policy)
            self.registry.put("policies", {"migrated": True})
        policies = self.registry.prefix_items("policy:", limit=1000)
        if len(policies) >= 1000:
            raise ValueError("Policy configuration exceeds bounded lookup; archive inactive policy records")
        return list(policies.values())

    def add_policy(self, policy: dict[str, Any]) -> dict[str, Any]:
        policy_id = str(policy.get("policy_id") or policy.get("name") or "").strip().lower().replace(" ", "-")
        if not policy_id or not isinstance(policy.get("rules"), dict):
            raise ValueError("policy_id/name and rules are required")
        operations = policy.get("operations", ["*"])
        if not isinstance(operations, list) or not operations or any(x not in {"*", "recommendations", "instance_bridge", "ontology_merge", "ontology_import"} for x in operations):
            raise ValueError("operations must name recommendations, instance_bridge, ontology_merge, ontology_import or *")
        self._validate_rules(policy["rules"])
        record = {"operations": sorted(set(operations)), "policy_id": policy_id, "name": str(policy.get("name") or policy_id), "rules": policy["rules"], "active": bool(policy.get("active", True)), "updated_at": datetime.now(timezone.utc).isoformat()}
        self.registry.put(f"policy:{policy_id}", record)
        return record

    def evaluate_policies(self, decision: dict[str, Any], exception_policy_ids: list[str] | None = None) -> dict[str, Any]:
        if exception_policy_ids:
            raise ValueError("Policy exceptions require a governed exception contract; caller overrides are disabled")
        return self.evaluate_decisions(str(decision.get("operation") or ""), [decision])

    @staticmethod
    def _validate_rules(rules):
        allowed = {"min_confidence", "required_outcomes", "required_metadata", "max_reasoning_length"}
        if not rules or set(rules) - allowed:
            raise ValueError("Unsupported or empty Semantica decision rules")
        confidence = rules.get("min_confidence", .7)
        if type(confidence) not in (int, float) or not 0 <= confidence <= 1:
            raise ValueError("min_confidence must be between 0 and 1")
        for key, default in (("required_outcomes", ["approved", "rejected", "flagged"]), ("required_metadata", ["decision_maker"])):
            values = rules.get(key, default)
            if not isinstance(values, list) or any(not isinstance(x, str) or not x for x in values):
                raise ValueError(key + " must be a list of nonempty strings")
        if type(rules.get("max_reasoning_length", 1000)) is not int or rules.get("max_reasoning_length", 1000) < 1:
            raise ValueError("max_reasoning_length must be a positive integer")

    def evaluate_decisions(self, operation, decisions):
        """One policy snapshot for the entire bounded batch; retain evidence separately."""
        if not isinstance(operation, str) or operation not in {'', 'recommendations', 'instance_bridge', 'ontology_merge', 'ontology_import'}:
            raise ValueError("Unknown decision policy operation")
        if not isinstance(decisions, list) or not 1 <= len(decisions) <= 2000:
            raise ValueError("A policy batch requires 1 to 2000 decisions")
        for item in decisions:
            if not isinstance(item, dict):
                raise ValueError("Decisions must be objects")
            confidence = item.get("confidence", 0)
            if type(confidence) not in (int, float) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
                raise ValueError("Decision confidence must be a finite number between 0 and 1")
            if not isinstance(item.get("reasoning", ""), str):
                raise ValueError("Decision reasoning must be text")
        policies = sorted([p for p in self._policies() if p.get("active", True) and
            ("*" in p.get("operations", ["*"]) or operation in p.get("operations", []))], key=lambda p: p["policy_id"])
        if len(policies) > 32:
            raise ValueError("At most 32 active policies may govern one decision operation")
        checks = []
        engine = ContextGraph()
        for policy in policies:
            self._validate_rules(policy["rules"])
            # Native Semantica requires the defaults to be supplied when any rules exist.
            rules = {"min_confidence": .7, "required_outcomes": ["approved", "rejected", "flagged"],
                     "required_metadata": ["decision_maker"], "max_reasoning_length": 1000, **policy["rules"]}
            for index, decision in enumerate(decisions):
                result = serialise(engine.enforce_decision_policy(decision, rules))
                result.pop("policy_rules", None)
                checks.append({"policy_id": policy["policy_id"], "decision_index": index, "subject": str(decision.get("candidate_label") or decision.get("kind") or "Reviewed ontology artifact")[:500], **result})
        from backend.depo_platform.bridge_contract import digest
        report = {"engine": "semantica.ContextGraph.enforce_decision_policy", "operation": operation,
            "status": "not_configured" if not policies else ("passed" if all(c["compliant"] for c in checks) else "blocked"),
            "compliant": all(c["compliant"] for c in checks) if policies else None,
            "blocking": any(not c["compliant"] for c in checks), "checks": checks[:200],
            "checks_total": len(checks), "checks_truncated": len(checks) > 200,
            "checks_digest": digest(checks),
            "blocked_decision_indices": sorted({c["decision_index"] for c in checks if not c["compliant"]}),
            "blocking_policy_ids": sorted({c["policy_id"] for c in checks if not c["compliant"]}),
            "policy_digest": digest(policies), "decision_digest": digest(decisions),
            "authorization": "Evidence only; existing validation and approval gates still apply"}
        report["assessment_id"] = "decision-policy-" + digest(report)
        evidence = {**report, "evaluated_at": datetime.now(timezone.utc).isoformat(), "decisions": decisions, "checks": checks}
        # Never mix potentially large audit records into the policy configuration registry.
        self._retain_assessment(report["assessment_id"], evidence)
        return report

    def _retain_assessment(self, key, evidence):
        PostgresRegistry("semantic_decision_assessments").put(key, evidence)

    def quality_gate(self, *, entities: list[dict[str, Any]], deduplicate: bool, conflict_property: str | None,
                     merge_strategy: str = "keep_most_complete", deduplication_mode: str = "similarity") -> dict[str, Any]:
        if deduplication_mode not in {'similarity', 'resource_identity'}:
            raise ValueError('Unknown quality deduplication mode')
        if deduplication_mode == 'resource_identity':
            # RDF identity is its complete IRI. Similar namespace strings or
            # generated IDs are not evidence that different resources duplicate.
            from urllib.parse import urlsplit
            seen, duplicates = set(), []
            for entity in entities:
                identity = entity.get('id')
                if not isinstance(identity, str) or not urlsplit(identity).scheme or any(c.isspace() for c in identity):
                    raise ValueError('Resource-identity quality review requires absolute IRIs')
                if identity in seen and deduplicate:
                    duplicates.append({'id': identity, 'reason': 'repeated_resource_identity'})
                seen.add(identity)
            conflicts = detect_conflicts(entities, property_name=conflict_property) if conflict_property else []
            return {'entities_received':len(entities), 'entities_semantically_reviewed':0,
                    'review_mode':'resource_identity', 'semantic_similarity_checked':False,
                    'consistency_verified':False, 'duplicates':duplicates, 'merge_operations':[],
                    'conflicts':serialise(conflicts), 'resolutions':[],
                    'publish_recommended':not duplicates and not conflicts}
        # Semantica's similarity deduplication is intentionally exhaustive.
        # Running it across a multi-thousand-term standard schema is quadratic
        # and can starve the service.  For large inputs, first use a stable,
        # lossless normalized-name index and ask Semantica to review only true
        # collision groups.  The response records the bounded review mode so a
        # caller never mistakes it for a full semantic similarity pass.
        full_limit = max(1, int(os.getenv("SEMANTIC_FULL_DEDUPLICATION_LIMIT", "500")))
        review_entities = entities
        review_mode = "full"
        if deduplicate and len(entities) > full_limit:
            groups: dict[str, list[dict[str, Any]]] = {}
            for entity in entities:
                name = str(entity.get("name") or entity.get("id") or "").strip().casefold()
                if name:
                    groups.setdefault(name, []).append(entity)
            review_entities = [entity for group in groups.values() if len(group) > 1 for entity in group]
            review_mode = "normalized-name-collisions"
        duplicates = detect_duplicates(review_entities) if deduplicate and review_entities else []
        merges = merge_entities(review_entities, method=merge_strategy) if deduplicate and review_entities else []
        conflicts = detect_conflicts(entities, property_name=conflict_property) if conflict_property else []
        resolutions = resolve_conflicts(conflicts) if conflicts else []
        return {
            "entities_received": len(entities), "entities_semantically_reviewed": len(review_entities), "review_mode": review_mode,
            "duplicates": serialise(duplicates), "merge_operations": serialise(merges),
            "conflicts": serialise(conflicts), "resolutions": serialise(resolutions),
            "publish_recommended": not duplicates and not conflicts,
        }

    def create_version(self, *, ontology: dict[str, Any], label: str, author: str, description: str) -> dict[str, Any]:
        principal = str(author or '').strip()
        if not principal:
            raise ValueError('Version author is required')
        # Semantica's changelog accepts email-shaped authors only. DEPO also
        # authenticates service principals; adapt their representation without
        # changing the actual approval identity or treating it as an email.
        is_email = re.fullmatch(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', principal) is not None
        sdk_author = principal if is_email else 'principal-' + hashlib.sha256(principal.encode()).hexdigest()[:32] + '@principals.pmem.invalid'
        manager = self._version_manager()
        snapshot = serialise(manager.create_snapshot(ontology, label, sdk_author, description,
            metadata={'authenticated_author': principal, 'author_representation': 'email' if is_email else 'service-principal-alias'}))
        snapshot['author'] = principal
        snapshot['sdk_author'] = sdk_author
        self.registry.put(f"version:{label}", snapshot)
        return snapshot

    def create_merge_version(self, *, ontology: dict[str, Any], author: str) -> dict[str, Any]:
        """A merge artifact has one immutable identity and one retained snapshot."""
        identifier = ontology.get('ontology_id')
        if not isinstance(identifier, str) or not identifier:
            raise ValueError('Merge version requires an ontology identity')
        label = 'merge:' + identifier
        retained = self.registry.get('version:' + label)
        if retained is not None:
            return retained
        return self.create_version(ontology=ontology, label=label, author=author,
                                   description='Approved ontology merge')

    def list_versions(self) -> list[dict[str, Any]]:
        return serialise(self._version_manager().list_versions())

    def compare_versions(self, older: str, newer: str) -> dict[str, Any]:
        return serialise(self._version_manager().compare_versions(older, newer))

    def _version_manager(self) -> OntologyVersionManager:
        """Hydrate Semantica's native manager from durable PostgreSQL snapshots."""
        manager = OntologyVersionManager(storage_path=None)
        for key, snapshot in self.registry.all().items():
            if not key.startswith("version:") or not isinstance(snapshot, dict):
                continue
            manager.storage.save(snapshot)
            manager.versions[str(snapshot.get("label") or key.removeprefix("version:"))] = snapshot
        return manager

    def analytics(self, graph: dict[str, Any]) -> dict[str, Any]:
        analyzer = GraphAnalyzer()
        return serialise(analyzer.analyze_graph(graph))
