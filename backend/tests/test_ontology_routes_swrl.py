from backend.routes.ontology_routes import SwrlRuleRequest


def test_swrl_route_request_accepts_nested_rule_payload():
    request = SwrlRuleRequest(
        rule={
            "rule_id": "nested-rule",
            "expression": "satisfies(?req, ?func) -> tracedTo(?req, ?func)",
            "use_case": "traceability",
        }
    )

    payload = request.rule_payload()

    assert payload["rule_id"] == "nested-rule"
    assert payload["expression"] == "satisfies(?req, ?func) -> tracedTo(?req, ?func)"
    assert payload["use_case"] == "traceability"


def test_swrl_route_request_accepts_flat_legacy_payload():
    request = SwrlRuleRequest(
        rule_id="flat-rule",
        name="Flat preview",
        expression="allocatedTo(?func, ?part) -> linkedTo(?func, ?part)",
        use_case="bridge_preview",
    )

    payload = request.rule_payload()

    assert payload["rule_id"] == "flat-rule"
    assert payload["name"] == "Flat preview"
    assert payload["expression"] == "allocatedTo(?func, ?part) -> linkedTo(?func, ?part)"
    assert payload["use_case"] == "bridge_preview"
