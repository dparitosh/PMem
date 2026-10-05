import unittest
from typing import Any
from backend.tests.test_semantic_artifact_boundaries import load_function

class QifAp242AgentTests(unittest.TestCase):
    def setup_agent(self):
        class Taxonomy:
            @staticmethod
            def _resolve_metadata(identifier): return {"ontology_id": identifier, "prefix": identifier}
        source = {"term_index": [{"kind": "Class", "label": "Feature", "iri": "urn:qif:a"}, {"kind": "Class", "label": "Feature", "iri": "urn:qif:b"}]}
        def plan(metadata, ontology_summary):
            return {"alignment_candidates": [{"source": "Feature", "source_category": "entities", "target_iri": "urn:ap242:feature"}]}
        return load_function("backend/agentic_service/ontology_orchestrator.py", "review_qif_ap242", {
            "Any": Any, "OntologyTaxonomyService": Taxonomy, "_resolve_ontology_path": lambda path, identifier: identifier,
            "inspect_ontology": lambda identifier: source, "plan_bridge": plan, "_review_summary": lambda value: {"issues": []}})
    def test_duplicate_labels_preserve_source_identity_ambiguity(self):
        result = self.setup_agent()({"qif_ontology_id": "qif_v1", "ap242_ontology_id": "ap242_v1"})
        candidate = result["steps"][-1]["result"]["alignment_candidates"][0]
        self.assertEqual(candidate["source_iris"], ["urn:qif:a", "urn:qif:b"])
        self.assertTrue(candidate["source_identity_ambiguous"])
        self.assertEqual(result["publication"], "requires_human_approval")
    def test_rejects_same_and_wrong_standard_ids(self):
        agent = self.setup_agent()
        for payload in [{"qif_ontology_id": "qif_v1", "ap242_ontology_id": "qif_v1"}, {"qif_ontology_id": "plmxml", "ap242_ontology_id": "ap242_v1"}]:
            with self.assertRaises(ValueError): agent(payload)
