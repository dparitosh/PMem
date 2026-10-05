import ast
import asyncio
import hashlib
import json
import os
from datetime import datetime
from typing import Any, Dict
from pathlib import Path
from types import SimpleNamespace
import unittest
from backend.Services.workflow_boundaries import chunk_size, taxonomy_forest

ROOT = Path(__file__).resolve().parents[1]


class ArtifactWorkflowTests(unittest.IsolatedAsyncioTestCase):
    def test_chunk_size_rejects_invalid_values(self):
        for value in [0, -1, True, [], {}, 1.5, "bad", "0", 10001]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                chunk_size(value)
        self.assertEqual(chunk_size(None), 80)
        self.assertEqual(chunk_size("25"), 25)

    def test_taxonomy_covers_rooted_and_disconnected_cyclic_components(self):
        nodes = [{"term_id": key, "label": key} for key in ["A", "B", "C", "D", "E"]]
        edges = [{"source_term": child, "target_term": parent} for child, parent in [("B", "A"), ("C", "D"), ("D", "C"), ("E", "E")]]
        roots, trees = taxonomy_forest(nodes, edges)
        stack, seen = list(trees), set()
        while stack:
            node = stack.pop()
            seen.add(node["term_id"])
            stack.extend(node["children"])
        self.assertEqual(seen, {"A", "B", "C", "D", "E"})
        self.assertEqual(len(roots), 3)

    async def test_source_profile_retries_use_the_same_registration_identity(self):
        calls = []
        class Response:
            def __init__(self, payload): self.payload = payload
            def raise_for_status(self): pass
            def json(self): return self.payload
        class Client:
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
            async def post(self, url, **kw):
                if url.endswith("evaluate"): return Response({"compliant": True})
                if url.endswith("quality-gate"): return Response({"publish_recommended": True})
                if url.endswith("generate"): return Response({"artifacts": {"turtle": "rdf"}})
                calls.append(kw["data"]["source"])
                return Response({"ontology_id": "demo_1"})
        tree = ast.parse((ROOT / "ingestion_service/workflow.py").read_text(encoding="utf-8"))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef))
        scope = {"Any": object, "os": os, "json": json, "hashlib": hashlib,
                 "service_url": lambda key, fallback: fallback, "service_bearer_headers": lambda *a, **kw: {},
                 "httpx": SimpleNamespace(AsyncClient=lambda **kw: Client())}
        exec(compile(ast.Module(body=[cls], type_ignores=[]), "workflow", "exec"), scope)
        runner = scope["SemanticIngestionWorkflow"]()
        kwargs = {"normalized": {"entities": [{"id": "1"}], "relationships": [], "records_processed": 1, "provenance": {}},
                  "name": "Demo", "prefix": "demo", "base_uri": "urn:demo:", "publish": True}
        for _ in range(2):
            result = await runner.run(**kwargs)
            self.assertEqual(result["status"], "awaiting_approval")
        self.assertEqual(calls[0], calls[1])
        self.assertRegex(calls[0], r"^source-profile-workflow:[0-9a-f]{64}$")

    def test_validation_failure_is_not_reported_as_success(self):
        tree = ast.parse((ROOT / "Services/semantic_workflow_service.py").read_text(encoding="utf-8"))
        fn = next(n for n in ast.walk(tree) if getattr(n, "name", None) == "validate_ontology")
        fn.decorator_list = []
        artifacts = SimpleNamespace(write_json=lambda *args: None, get_manifest=lambda task: {})
        scope = {"Dict": Dict, "Any": Any, "Path": Path, "datetime": datetime, "WorkflowArtifactService": artifacts}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), "workflow", "exec"), scope)
        metadata = {"prefix": "demo", "ontology_name": "Demo", "file_path": __file__}
        fake = SimpleNamespace(_resolve_ontology_id=lambda value: value, _ontology_metadata=lambda oid: metadata,
                               _read_ontology_file=lambda meta: "https://example.test/ontology", _new_task=lambda *args: "run_1")
        def unavailable(meta): raise ImportError("validator unavailable")
        scope["validate_semantic_artifact"] = unavailable
        result = scope["validate_ontology"](fake, {"ontology_id": "demo"})
        self.assertEqual(result["status"], "quality_warning")
        self.assertEqual(result["result"]["summary"]["errors"], 1)
        scope["validate_semantic_artifact"] = lambda meta: {"shacl": {"conforms": False}, "consistency": {"status": "passed"}}
        result = scope["validate_ontology"](fake, {"ontology_id": "demo"})
        self.assertEqual(result["status"], "quality_warning")

    def test_express_upload_and_materialization_are_supported(self):
        for relative, name in [("Services/unified_import_router.py", "upload_ontology_file"),
                               ("Services/ontology_upload_manager.py", "_materialize_semantic_artifacts")]:
            tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
            fn = next(n for n in ast.walk(tree) if getattr(n, "name", None) == name)
            self.assertTrue(any(isinstance(n, ast.Constant) and n.value == "express" for n in ast.walk(fn)))


if __name__ == "__main__":
    unittest.main()
