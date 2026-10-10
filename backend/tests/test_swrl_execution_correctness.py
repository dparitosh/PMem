import unittest

from backend.Services.swrl_reasoning_service import (
    ApplicationRuleExecutor as Executor, SemanticFact, SwrlAtom, SwrlRuleService,
)


class SwrlCorrectnessTests(unittest.TestCase):
    def test_builtin_order_does_not_discard_binding(self):
        rule = SwrlRuleService.parse_rule({
            "expression": "swrlb:greaterThan(?v, 10) ^ value(?x, ?v) -> high(?x)",
        })
        result = Executor.execute(rule, [SemanticFact("item", "value", "12")], "run")
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["inferred_facts"][0]["subject"], "item")

    def test_enabled_rejects_string_false(self):
        with self.assertRaises(ValueError):
            SwrlRuleService.parse_rule({"enabled": "false"})

    def test_builtin_requires_two_arguments(self):
        rule = SwrlRuleService.parse_rule({"expression": "swrlb:equal(x) -> high(x)"})
        self.assertFalse(SwrlRuleService.validate(rule)["valid"])

    def test_string_comparisons_are_case_sensitive(self):
        self.assertFalse(Executor._builtin_matches(SwrlAtom("swrlb:contains", ("ABC", "a")), {}))
        self.assertFalse(Executor._builtin_matches(SwrlAtom("swrlb:startsWith", ("ABC", "a")), {}))

    def test_nonfinite_numeric_input_cannot_infer(self):
        self.assertFalse(Executor._builtin_matches(SwrlAtom("swrlb:greaterThan", ("inf", "1")), {}))


if __name__ == "__main__":
    unittest.main()
