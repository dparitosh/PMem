"""SWRL-style rule validation and execution abstraction.

Neo4j does not run SWRL natively. This service validates and executes a safe
subset in application code, and exposes Cypher plans only for materializing
already-approved inferred facts with provenance.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


SUPPORTED_BUILTINS = {
    "swrlb:equal",
    "swrlb:notEqual",
    "swrlb:contains",
    "swrlb:startsWith",
    "swrlb:greaterThan",
    "swrlb:lessThan",
}


@dataclass(frozen=True)
class SwrlAtom:
    predicate: str
    arguments: Tuple[str, ...]

    @property
    def is_builtin(self) -> bool:
        return self.predicate.startswith("swrlb:") or self.predicate in SUPPORTED_BUILTINS

    @property
    def variables(self) -> Tuple[str, ...]:
        return tuple(arg for arg in self.arguments if arg.startswith("?"))

    def text(self) -> str:
        return f"{self.predicate}({', '.join(self.arguments)})"


@dataclass(frozen=True)
class SwrlRule:
    rule_id: str
    name: str
    body: Tuple[SwrlAtom, ...]
    head: Tuple[SwrlAtom, ...]
    version: str = "1"
    enabled: bool = True
    use_case: str = "general"

    def preview(self) -> str:
        return " IF " + " AND ".join(atom.text() for atom in self.body) + " THEN " + " AND ".join(atom.text() for atom in self.head)


@dataclass(frozen=True)
class SemanticFact:
    subject: str
    predicate: str
    object: str
    fact_id: str = ""
    asserted: bool = True
    properties: Mapping[str, Any] = field(default_factory=dict)

    def key(self) -> Tuple[str, str, str]:
        return (self.subject, self.predicate, self.object)


@dataclass(frozen=True)
class InferredFact:
    subject: str
    predicate: str
    object: str
    rule_id: str
    source_facts: Tuple[str, ...]
    execution_id: str
    version: str
    timestamp: str
    asserted: bool = False
    inferred: bool = True

    def key(self) -> Tuple[str, str, str, str]:
        return (self.rule_id, self.subject, self.predicate, self.object)


class SwrlRuleService:
    """Parser and validator for SWRL-style rules."""

    ATOM_RE = re.compile(r"^\s*([A-Za-z_][\w:.-]*)\s*\((.*)\)\s*$")

    @classmethod
    def parse_rule(cls, payload: Mapping[str, Any]) -> SwrlRule:
        expression = str(payload.get("expression") or payload.get("rule") or "").strip()
        if expression:
            if "->" in expression:
                body_text, head_text = expression.split("->", 1)
            elif "=>" in expression:
                body_text, head_text = expression.split("=>", 1)
            else:
                raise ValueError("SWRL rule must contain -> or =>")
            body = cls.parse_atoms(body_text)
            head = cls.parse_atoms(head_text)
        else:
            body = tuple(cls._atom_from_mapping(atom) for atom in payload.get("body") or [])
            head = tuple(cls._atom_from_mapping(atom) for atom in payload.get("head") or [])

        rule_id = str(payload.get("rule_id") or payload.get("id") or payload.get("name") or "rule").strip()
        return SwrlRule(
            rule_id=rule_id,
            name=str(payload.get("name") or rule_id).strip(),
            body=body,
            head=head,
            version=str(payload.get("version") or "1").strip(),
            enabled=bool(payload.get("enabled", True)),
            use_case=str(payload.get("use_case") or payload.get("useCase") or "general").strip(),
        )

    @classmethod
    def parse_atoms(cls, text: str) -> Tuple[SwrlAtom, ...]:
        atoms: List[SwrlAtom] = []
        for raw in re.split(r"\s*\^\s*|\s+AND\s+", text, flags=re.IGNORECASE):
            raw = raw.strip()
            if not raw:
                continue
            match = cls.ATOM_RE.match(raw)
            if not match:
                raise ValueError(f"Invalid SWRL atom: {raw}")
            args = tuple(arg.strip().strip('"') for arg in match.group(2).split(",") if arg.strip())
            atoms.append(SwrlAtom(match.group(1), args))
        return tuple(atoms)

    @staticmethod
    def _atom_from_mapping(raw: Mapping[str, Any]) -> SwrlAtom:
        return SwrlAtom(
            predicate=str(raw.get("predicate") or "").strip(),
            arguments=tuple(str(arg).strip() for arg in raw.get("arguments") or [] if str(arg or "").strip()),
        )

    @staticmethod
    def validate(rule: SwrlRule) -> Dict[str, Any]:
        issues: List[Dict[str, Any]] = []
        if not rule.body:
            issues.append({"severity": "error", "code": "empty_body", "message": "Rule body is required"})
        if not rule.head:
            issues.append({"severity": "error", "code": "empty_head", "message": "Rule head is required"})

        body_vars = {var for atom in rule.body for var in atom.variables}
        body_fact_vars = {var for atom in rule.body if not atom.is_builtin for var in atom.variables}
        head_vars = {var for atom in rule.head for var in atom.variables}
        unbound = sorted(head_vars - body_vars)
        if unbound:
            issues.append({
                "severity": "error",
                "code": "unbound_variable",
                "message": "Head variables must be bound in the rule body",
                "variables": unbound,
            })

        builtin_unbound = sorted({
            var
            for atom in rule.body
            if atom.is_builtin
            for var in atom.variables
            if var not in body_fact_vars
        })
        if builtin_unbound:
            issues.append({
                "severity": "error",
                "code": "unbound_builtin_variable",
                "message": "Built-in variables must be bound by a class or property atom in the rule body",
                "variables": builtin_unbound,
            })

        body_predicates = {atom.predicate for atom in rule.body if not atom.is_builtin}
        for atom in (*rule.body, *rule.head):
            if not atom.predicate:
                issues.append({"severity": "error", "code": "missing_predicate", "message": "Atom predicate is required"})
            if atom.is_builtin and atom.predicate not in SUPPORTED_BUILTINS:
                issues.append({
                    "severity": "error",
                    "code": "unsupported_builtin",
                    "message": f"Unsupported SWRL built-in: {atom.predicate}",
                    "predicate": atom.predicate,
                })
            if len(atom.arguments) not in (1, 2):
                issues.append({
                    "severity": "error",
                    "code": "invalid_arity",
                    "message": f"Atom {atom.text()} must have one or two arguments",
                    "atom": atom.text(),
                })
        for atom in rule.head:
            if atom.is_builtin:
                issues.append({"severity": "error", "code": "builtin_in_head", "message": "Built-ins are not supported in rule head"})
            if atom.predicate in body_predicates:
                issues.append({
                    "severity": "error",
                    "code": "recursive_rule",
                    "message": f"Rule head predicate {atom.predicate} also appears in the body",
                    "predicate": atom.predicate,
                })

        supported = not any(issue["severity"] == "error" for issue in issues)
        return {
            "valid": supported,
            "supported": supported,
            "issues": issues,
            "preview": rule.preview(),
            "rule": SwrlRuleService.to_dict(rule),
        }

    @staticmethod
    def to_dict(rule: SwrlRule) -> Dict[str, Any]:
        return {
            "rule_id": rule.rule_id,
            "name": rule.name,
            "version": rule.version,
            "enabled": rule.enabled,
            "use_case": rule.use_case,
            "body": [{"predicate": atom.predicate, "arguments": list(atom.arguments)} for atom in rule.body],
            "head": [{"predicate": atom.predicate, "arguments": list(atom.arguments)} for atom in rule.head],
            "preview": rule.preview(),
        }


class ApplicationRuleExecutor:
    """Application-level execution for a safe SWRL subset over fact triples."""

    @staticmethod
    def execute(
        rule: SwrlRule,
        facts: Sequence[SemanticFact],
        execution_id: str,
        version: Optional[str] = None,
    ) -> Dict[str, Any]:
        validation = SwrlRuleService.validate(rule)
        if not validation["supported"]:
            return {
                "status": "unsupported",
                "rule_id": rule.rule_id,
                "validation": validation,
                "inferred_facts": [],
            }

        bindings = ApplicationRuleExecutor._match_body(rule.body, facts)
        timestamp = datetime.now(timezone.utc).isoformat()
        inferred_by_key: Dict[Tuple[str, str, str, str], InferredFact] = {}
        for binding, source_fact_ids in bindings:
            for head_atom in rule.head:
                if len(head_atom.arguments) == 1:
                    subject = ApplicationRuleExecutor._resolve_arg(head_atom.arguments[0], binding)
                    obj = head_atom.predicate
                    predicate = "rdf:type"
                else:
                    subject = ApplicationRuleExecutor._resolve_arg(head_atom.arguments[0], binding)
                    obj = ApplicationRuleExecutor._resolve_arg(head_atom.arguments[1], binding)
                    predicate = head_atom.predicate
                if not subject or not obj:
                    continue
                inferred = InferredFact(
                    subject=subject,
                    predicate=predicate,
                    object=obj,
                    rule_id=rule.rule_id,
                    source_facts=tuple(sorted(set(source_fact_ids))),
                    execution_id=execution_id,
                    version=version or rule.version,
                    timestamp=timestamp,
                )
                inferred_by_key[inferred.key()] = inferred

        return {
            "status": "success",
            "rule_id": rule.rule_id,
            "execution_id": execution_id,
            "version": version or rule.version,
            "inferred_facts": [ApplicationRuleExecutor.fact_to_dict(fact) for fact in inferred_by_key.values()],
            "summary": {
                "source_facts": len(facts),
                "bindings": len(bindings),
                "inferred_facts": len(inferred_by_key),
            },
            "validation": validation,
        }

    @staticmethod
    def _match_body(body: Sequence[SwrlAtom], facts: Sequence[SemanticFact]) -> List[Tuple[Dict[str, str], List[str]]]:
        bindings: List[Tuple[Dict[str, str], List[str]]] = [({}, [])]
        for atom in body:
            if atom.is_builtin:
                bindings = [
                    (binding, fact_ids)
                    for binding, fact_ids in bindings
                    if ApplicationRuleExecutor._builtin_matches(atom, binding)
                ]
                continue

            next_bindings: List[Tuple[Dict[str, str], List[str]]] = []
            for binding, fact_ids in bindings:
                for fact in facts:
                    candidate = ApplicationRuleExecutor._match_atom(atom, fact, binding)
                    if candidate is not None:
                        fact_id = fact.fact_id or "|".join(fact.key())
                        next_bindings.append((candidate, [*fact_ids, fact_id]))
            bindings = next_bindings
        return bindings

    @staticmethod
    def _match_atom(atom: SwrlAtom, fact: SemanticFact, binding: Mapping[str, str]) -> Optional[Dict[str, str]]:
        next_binding = dict(binding)
        if len(atom.arguments) == 1:
            if fact.predicate != "rdf:type" or fact.object != atom.predicate:
                return None
            return ApplicationRuleExecutor._bind(atom.arguments[0], fact.subject, next_binding)
        if fact.predicate != atom.predicate:
            return None
        next_binding = ApplicationRuleExecutor._bind(atom.arguments[0], fact.subject, next_binding)
        if next_binding is None:
            return None
        return ApplicationRuleExecutor._bind(atom.arguments[1], fact.object, next_binding)

    @staticmethod
    def _bind(arg: str, value: str, binding: Dict[str, str]) -> Optional[Dict[str, str]]:
        if arg.startswith("?"):
            if arg in binding and binding[arg] != value:
                return None
            binding[arg] = value
            return binding
        return binding if arg == value else None

    @staticmethod
    def _resolve_arg(arg: str, binding: Mapping[str, str]) -> str:
        return binding.get(arg, arg) if arg.startswith("?") else arg

    @staticmethod
    def _builtin_matches(atom: SwrlAtom, binding: Mapping[str, str]) -> bool:
        if len(atom.arguments) != 2:
            return False
        left = ApplicationRuleExecutor._resolve_arg(atom.arguments[0], binding)
        right = ApplicationRuleExecutor._resolve_arg(atom.arguments[1], binding)
        if atom.predicate == "swrlb:equal":
            return left == right
        if atom.predicate == "swrlb:notEqual":
            return left != right
        if atom.predicate == "swrlb:contains":
            return right.casefold() in left.casefold()
        if atom.predicate == "swrlb:startsWith":
            return left.casefold().startswith(right.casefold())
        if atom.predicate in {"swrlb:greaterThan", "swrlb:lessThan"}:
            try:
                left_num = float(left)
                right_num = float(right)
            except ValueError:
                return False
            return left_num > right_num if atom.predicate == "swrlb:greaterThan" else left_num < right_num
        return False

    @staticmethod
    def fact_to_dict(fact: InferredFact) -> Dict[str, Any]:
        return {
            "subject": fact.subject,
            "predicate": fact.predicate,
            "object": fact.object,
            "ruleId": fact.rule_id,
            "sourceFacts": list(fact.source_facts),
            "executionId": fact.execution_id,
            "timestamp": fact.timestamp,
            "version": fact.version,
            "asserted": fact.asserted,
            "inferred": fact.inferred,
        }


class InferenceNeo4jRepository:
    """Parameterized Cypher plans for rules, executions, and inferred facts."""

    @staticmethod
    def materialization_plan(rule: SwrlRule, inferred_facts: Sequence[Mapping[str, Any]], execution_id: str) -> List[Dict[str, Any]]:
        rows = []
        for row in inferred_facts:
            next_row = dict(row)
            next_row["factKey"] = "|".join([
                str(next_row.get("ruleId") or rule.rule_id),
                str(next_row.get("subject") or ""),
                str(next_row.get("predicate") or ""),
                str(next_row.get("object") or ""),
            ])
            rows.append(next_row)
        fact_keys = [row["factKey"] for row in rows]
        timestamp = datetime.now(timezone.utc).isoformat()
        return [
            {
                "name": "rule_constraints",
                "cypher": "CREATE CONSTRAINT semantic_rule_id IF NOT EXISTS FOR (r:SemanticRule) REQUIRE r.ruleId IS UNIQUE",
                "params": {},
            },
            {
                "name": "upsert_rule",
                "cypher": (
                    "MERGE (r:SemanticRule {ruleId: $ruleId}) "
                    "SET r.name = $name, r.version = $version, r.enabled = $enabled, "
                    "r.useCase = $useCase, r.preview = $preview, r.updatedAt = $updatedAt"
                ),
                "params": {
                    "ruleId": rule.rule_id,
                    "name": rule.name,
                    "version": rule.version,
                    "enabled": rule.enabled,
                    "useCase": rule.use_case,
                    "preview": rule.preview(),
                    "updatedAt": timestamp,
                },
            },
            {
                "name": "record_execution",
                "cypher": (
                    "MERGE (e:RuleExecution {executionId: $executionId}) "
                    "SET e.ruleId = $ruleId, e.version = $version, e.timestamp = $timestamp"
                ),
                "params": {"executionId": execution_id, "ruleId": rule.rule_id, "version": rule.version, "timestamp": timestamp},
            },
            {
                "name": "remove_stale_inferred_facts",
                "cypher": (
                    "MATCH ()-[r:INFERRED_FACT {ruleId: $ruleId}]->() "
                    "WHERE coalesce(r.version, '') <> $version OR NOT coalesce(r.factKey, '') IN $factKeys "
                    "DELETE r"
                ),
                "params": {"ruleId": rule.rule_id, "version": rule.version, "factKeys": fact_keys},
            },
            {
                "name": "merge_inferred_facts",
                "cypher": (
                    "UNWIND $rows AS row "
                    "MERGE (s:SemanticResource {businessId: row.subject}) "
                    "MERGE (o:SemanticResource {businessId: row.object}) "
                    "MERGE (s)-[r:INFERRED_FACT {factKey: row.factKey}]->(o) "
                    "SET r.ruleId = row.ruleId, r.predicate = row.predicate, r.object = row.object, "
                    "r.sourceFacts = row.sourceFacts, r.executionId = row.executionId, "
                    "r.timestamp = row.timestamp, r.version = row.version, "
                    "r.asserted = false, r.inferred = true"
                ),
                "params": {"rows": rows},
            },
        ]
