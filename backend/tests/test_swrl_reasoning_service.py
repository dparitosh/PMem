from backend.Services.swrl_reasoning_service import (
    ApplicationRuleExecutor,
    InferenceNeo4jRepository,
    SemanticFact,
    SwrlRuleService,
)


def test_swrl_rule_parser_and_if_then_preview():
    rule = SwrlRuleService.parse_rule({
        "rule_id": "traceability-impact",
        "expression": "satisfies(?req, ?func) ^ allocatedTo(?func, ?part) -> impactedBy(?req, ?part)",
        "use_case": "change_impact",
    })

    validation = SwrlRuleService.validate(rule)

    assert validation["valid"] is True
    assert "IF satisfies(?req, ?func)" in validation["preview"]
    assert validation["rule"]["use_case"] == "change_impact"


def test_swrl_validation_detects_unbound_variables_and_unsupported_builtins():
    rule = SwrlRuleService.parse_rule({
        "rule_id": "bad-risk",
        "expression": "riskScore(?x, ?score) ^ swrlb:pow(?score, 2) -> highRisk(?y)",
    })

    validation = SwrlRuleService.validate(rule)

    assert validation["supported"] is False
    assert any(issue["code"] == "unbound_variable" for issue in validation["issues"])
    assert any(issue["code"] == "unsupported_builtin" for issue in validation["issues"])


def test_swrl_validation_detects_unbound_builtin_variables():
    rule = SwrlRuleService.parse_rule({
        "rule_id": "unbound-built-in",
        "expression": "Requirement(?req) ^ swrlb:contains(?name, REQ) -> selected(?req)",
    })

    validation = SwrlRuleService.validate(rule)

    assert validation["valid"] is False
    assert any(issue["code"] == "unbound_builtin_variable" for issue in validation["issues"])


def test_swrl_validation_flags_recursive_rules():
    rule = SwrlRuleService.parse_rule({
        "rule_id": "recursive",
        "expression": "impacts(?a, ?b) -> impacts(?a, ?b)",
    })

    validation = SwrlRuleService.validate(rule)

    assert validation["valid"] is False
    assert any(issue["code"] == "recursive_rule" for issue in validation["issues"])


def test_application_executor_derives_idempotent_facts_with_provenance():
    rule = SwrlRuleService.parse_rule({
        "rule_id": "change-impact",
        "version": "2",
        "expression": "satisfies(?req, ?func) ^ allocatedTo(?func, ?part) -> impactedBy(?req, ?part)",
    })
    facts = [
        SemanticFact("REQ-001", "satisfies", "Function-01", "f1"),
        SemanticFact("REQ-001", "satisfies", "Function-01", "f1-duplicate"),
        SemanticFact("Function-01", "allocatedTo", "Part-99", "f2"),
    ]

    result = ApplicationRuleExecutor.execute(rule, facts, execution_id="exec-1")

    assert result["status"] == "success"
    assert result["summary"]["inferred_facts"] == 1
    inferred = result["inferred_facts"][0]
    assert inferred["subject"] == "REQ-001"
    assert inferred["predicate"] == "impactedBy"
    assert inferred["object"] == "Part-99"
    assert inferred["ruleId"] == "change-impact"
    assert inferred["executionId"] == "exec-1"
    assert inferred["version"] == "2"
    assert inferred["inferred"] is True
    assert inferred["asserted"] is False


def test_neo4j_materialization_plan_removes_stale_inferred_facts():
    rule = SwrlRuleService.parse_rule({
        "rule_id": "compliance",
        "version": "3",
        "expression": "violates(?item, ?standard) -> requiresReview(?item, ?standard)",
    })
    inferred = [{
        "subject": "Part-1",
        "predicate": "requiresReview",
        "object": "STD-1",
        "ruleId": "compliance",
        "sourceFacts": ["fact-1"],
        "executionId": "exec-7",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "version": "3",
    }]

    plan = InferenceNeo4jRepository.materialization_plan(rule, inferred, "exec-7")
    stale_step = next(step for step in plan if step["name"] == "remove_stale_inferred_facts")
    merge_step = next(step for step in plan if step["name"] == "merge_inferred_facts")

    assert "DELETE r" in stale_step["cypher"]
    assert stale_step["params"]["ruleId"] == "compliance"
    assert stale_step["params"]["version"] == "3"
    assert len(stale_step["params"]["factKeys"]) == 1
    assert len(stale_step["params"]["factKeys"][0]) == 64
    assert stale_step["params"]["scopeId"] == "exec-7"
    assert "scopeId: $scopeId" in stale_step["cypher"]
    assert "NOT coalesce(r.factKey, '') IN $factKeys" in stale_step["cypher"]
    assert "UNWIND $rows AS row" in merge_step["cypher"]
    assert "MERGE (s)-[r:INFERRED_FACT {factKey: row.factKey}]->(o)" in merge_step["cypher"]
    assert "Part-1" not in merge_step["cypher"]
    assert merge_step["params"]["rows"][0]["sourceFacts"] == ["fact-1"]
    assert merge_step["params"]["rows"][0]["factKey"] == stale_step["params"]["factKeys"][0]
