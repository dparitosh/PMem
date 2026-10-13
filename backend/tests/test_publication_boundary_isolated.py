"""Dependency-free execution checks for the publication/auth boundaries."""
import ast
import asyncio
import hashlib
import json
import unittest
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace


def definitions(path, names, scope):
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    nodes = [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names]
    for node in nodes:
        node.decorator_list = []
    exec(compile(ast.Module(body=nodes, type_ignores=[]), path, "exec"), scope)
    return scope


class PublicationBoundaryTests(unittest.TestCase):
    def test_catalog_reads_authenticate(self):
        def deny(request):
            raise PermissionError("missing credential")
        scope = definitions("backend/ontology_service/modeling_router.py", {"_modeling_identity"},
            {"Request": object, "graph_read_identity": deny})
        for method in ("GET", "HEAD", "OPTIONS"):
            with self.assertRaises(PermissionError):
                scope["_modeling_identity"](SimpleNamespace(method=method))

    def execute(self, state="approved", receipt_id="digest"):
        calls = []
        class Response:
            def __init__(self, value): self.value = value
            def raise_for_status(self): pass
            def json(self): return self.value
        class Client:
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
            async def get(self, url, **kwargs):
                self_test.assertEqual(kwargs["headers"]["Authorization"], "GRAPH_READ_TOKEN")
                return Response({"lifecycle_status": state})
            async def post(self, url, **kwargs):
                calls.append(url)
                if url.endswith("evaluate"): return Response({"compliant": True})
                if url.endswith("quality-gate"): return Response({"publish_recommended": True})
                if url.endswith("register"): return Response({"ontology_id": "demo"})
                self_test.assertEqual(url, "http://ontology/ontologies/demo/publish")
                return Response({"status": "published", "ontology_id": "demo", "publication_id": "digest",
                    "receipt": {"status": "success", "ontology_id": "demo", "publication_id": receipt_id,
                                "resources": 1, "relationships": 0}})
        self_test = self
        async def thread(fn, *args, **kwargs): return fn(*args, **kwargs)
        scope = definitions("backend/ingestion_service/engineering_workflow.py", {"_run", "_request", "_require_publishable"},
            {"Any": object, "Path":Path, "hashlib": hashlib, "json": json, "run_in_threadpool": thread,
             "dependency_stage": lambda *args: nullcontext(),
             "service_bearer_headers": lambda profile, **kwargs: {"Authorization": profile},
             "httpx": SimpleNamespace(AsyncClient=lambda **kwargs: Client()),
             "PathName": SimpleNamespace(safe_stem=lambda name: "demo")})
        workflow = SimpleNamespace(ontology_url="http://ontology", timeout=30, publication_timeout=600, _isolated_conversion=False,
            converter=SimpleNamespace(convert=lambda **kwargs: {"ontology": {"name": "demo", "prefix": "d", "turtle": ""}}),
            _governance_entities=lambda value: [], _request=scope["_request"], _require_publishable=scope["_require_publishable"])
        result = asyncio.run(scope["_run"](workflow, filename="demo.xsd", content=b"schema", publish=True))
        return result, calls

    def test_approved_publication_uses_ontology_service(self):
        result, calls = self.execute()
        self.assertEqual(result["status"], "published")
        self.assertEqual(len(calls), 4)

    def test_draft_does_not_publish(self):
        result, calls = self.execute(state="draft")
        self.assertEqual(result["status"], "approval_required")
        self.assertEqual(len(calls), 3)

    def test_wrong_receipt_is_not_success(self):
        with self.assertRaises(RuntimeError): self.execute(receipt_id="different-artifact")

    def test_retired_does_not_publish(self):
        with self.assertRaises(ValueError): self.execute(state="retired")


if __name__ == "__main__":
    unittest.main()
