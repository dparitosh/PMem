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

    def test_characteristic_join_scales_without_cartesian_rescans(self):
        rule = SwrlRuleService.parse_rule({'expression':
            'Inspection(?i) ^ measures(?i, ?c) ^ value(?i, ?v) ^ swrlb:greaterThan(?v, 30.024) -> AboveLimit(?i)'})
        facts = []
        for i in range(1000):
            identity = 'inspection-' + str(i)
            facts.extend([SemanticFact(identity, 'rdf:type', 'Inspection', 'type-' + str(i)),
                SemanticFact(identity, 'measures', 'shaft-characteristic', 'characteristic-' + str(i)),
                SemanticFact(identity, 'value', '30.025' if i == 999 else '30.020', 'measurement-' + str(i))])
        result = Executor.execute(rule, facts, 'scoped-run')
        self.assertEqual(len(result['inferred_facts']), 1)
        fact = result['inferred_facts'][0]
        self.assertEqual(fact['subject'], 'inspection-999')
        self.assertEqual(set(fact['sourceFacts']), {'type-999', 'characteristic-999', 'measurement-999'})

    def test_class_after_bound_property_does_not_depend_on_atom_order(self):
        rule=SwrlRuleService.parse_rule({'expression':'value(?i, ?v) ^ Inspection(?i) ^ swrlb:greaterThan(?v, 10) -> High(?i)'})
        facts=[fact for i in range(1200) for fact in (
            SemanticFact(str(i),'value','11' if i==1199 else '9'),
            SemanticFact(str(i),'rdf:type','Inspection'))]
        result=Executor.execute(rule,facts,'property-first')
        self.assertEqual([row['subject'] for row in result['inferred_facts']],['1199'])

    def test_numeric_limit_comparison_preserves_decimal_boundary(self):
        self.assertTrue(Executor._builtin_matches(SwrlAtom('swrlb:greaterThan',
            ('30.02400000000000000001', '30.024')), {}))
        self.assertFalse(Executor._builtin_matches(SwrlAtom('swrlb:greaterThan',
            ('30.024', '30.024')), {}))

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
