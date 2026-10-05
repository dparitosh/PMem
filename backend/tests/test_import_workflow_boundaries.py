"""Dependency-light checks of actual upload and workflow boundary code."""
import ast
import asyncio
from contextlib import nullcontext
import hashlib
import json
from pathlib import Path
import re
import threading
from types import SimpleNamespace, ModuleType
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def extract(relative, names, scope):
    tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
    nodes = [n for n in tree.body if getattr(n, "name", None) in names]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), relative, "exec"), scope)
    return scope


class HttpError(Exception):
    def __init__(self, status, detail):
        self.status_code, self.detail = status, detail


async def threadpool(fn, *args, **kwargs):
    return await asyncio.to_thread(fn, *args, **kwargs)


class ImportBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_upload_rejects_oversize_with_bounded_read(self):
        scope = extract("ingestion_service/router.py", {"_read_bounded_upload"},
                        {"UploadFile": object, "HTTPException": HttpError, "MAX_UPLOAD_BYTES": 4})
        sizes = []
        async def read(size):
            sizes.append(size)
            return b"12345"[:size]
        with self.assertRaises(HttpError) as error:
            await scope["_read_bounded_upload"](SimpleNamespace(read=read))
        self.assertEqual(error.exception.status_code, 413)
        self.assertEqual(sizes, [5])

    def test_policy_exceptions_reject_wrong_shapes_and_items(self):
        scope = extract("ingestion_service/router.py", {"_policy_exceptions"}, {"json": json})
        for raw in ['null', '42', '"abc"', '{}', '[1]', '[""]']:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                scope["_policy_exceptions"](raw)
        self.assertEqual(scope["_policy_exceptions"]('["review-1"]'), ["review-1"])

    async def test_quality_cannot_be_bypassed_and_converter_is_offloaded(self):
        calls = []
        worker_threads = []
        class Converter:
            def convert(self, **kwargs):
                worker_threads.append(threading.get_ident())
                return {"format": "XSD", "ontology": {"name": "Demo", "prefix": "demo", "turtle": "rdf"}}
        class Response:
            def __init__(self, payload): self.payload = payload
            def raise_for_status(self): pass
            def json(self): return self.payload
        class Client:
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
            async def post(self, url, **kwargs):
                calls.append(url)
                return Response({"compliant": True} if url.endswith("evaluate") else {"publish_recommended": False})
        scope = extract("ingestion_service/engineering_workflow.py", {"EngineeringWorkflow", "PathName"},
            {"EngineeringSchemaConverter": Converter, "Any": object, "service_url": lambda key, fallback: fallback,
             "os": __import__("os"), "httpx": SimpleNamespace(AsyncClient=lambda **kw: Client()),
             "run_in_threadpool": threadpool, "hashlib": hashlib, "json": json,
             "service_bearer_headers": lambda *args, **kw: {}})
        workflow = scope["EngineeringWorkflow"](Converter())
        workflow._governance_entities = lambda turtle: []
        result = await workflow.run(filename="demo.xsd", content=b"schema", publish=True, enforce_quality=False)
        self.assertEqual(result["status"], "quality_blocked")
        self.assertFalse(any(url.endswith("register") or url.endswith("publish") for url in calls))
        self.assertNotEqual(worker_threads[0], threading.get_ident())

    def test_publication_blocks_terminal_and_unknown_lifecycle_states(self):
        tree = ast.parse((ROOT / "ingestion_service/engineering_workflow.py").read_text(encoding="utf-8"))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "EngineeringWorkflow")
        method = next(n for n in cls.body if getattr(n, "name", None) == "_require_publishable")
        method.decorator_list = []
        scope = {"Any": object}
        exec(compile(ast.Module(body=[method], type_ignores=[]), "workflow", "exec"), scope)
        for state in ["retired", "deprecated", "unknown", None]:
            with self.subTest(state=state), self.assertRaises(ValueError):
                scope["_require_publishable"]({"lifecycle_status": state})
        with self.assertRaises(ValueError):
            scope["_require_publishable"]({"lifecycle_status": "approved", "status": "superseded"})
        scope["_require_publishable"]({"lifecycle_status": "approved", "status": "registered"})

    def test_retry_validation_rejects_reserved_fields_and_filename(self):
        tree = ast.parse((ROOT / "ontology_service/catalog.py").read_text(encoding="utf-8"))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "OntologyCatalog")
        method = next(n for n in cls.body if getattr(n, "name", None) == "_validate_registration")
        scope = {"Any": object, "Path": Path, "_safe_token": lambda value, **kw: value.strip()}
        exec(compile(ast.Module(body=[method], type_ignores=[]), "catalog", "exec"), scope)
        calls = []
        fake = SimpleNamespace(_parse_ontology=lambda content, filename: calls.append(filename) or {"rdf_format": "xml"})
        for kwargs in [{"content": b""}, {"filename": "metadata.json"}, {"extra_metadata": {"lifecycle_status": "approved"}}]:
            values = {"content": b"rdf", "filename": "demo.rdf", "prefix": "demo", **kwargs}
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                scope["_validate_registration"](fake, **values)
        self.assertFalse(calls)
        result = scope["_validate_registration"](fake, content=b"rdf", filename="demo.rdf", prefix=" demo ")
        self.assertEqual(result, ("demo", "demo.rdf", {"rdf_format": "xml"}))

    def test_all_ingestion_reads_are_bounded(self):
        tree = ast.parse((ROOT / "ingestion_service/router.py").read_text(encoding="utf-8"))
        reads = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                 and n.func.attr == "read"]
        self.assertEqual(len(reads), 1)
        self.assertTrue(reads[0].args)

    def test_registration_retry_reuses_artifact_and_rejects_conflicts(self):
        tree = ast.parse((ROOT / "ontology_service/catalog.py").read_text(encoding="utf-8"))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "OntologyCatalog")
        method = next(n for n in cls.body if getattr(n, "name", None) == "register")
        scope = {"Any": object, "re": re, "nullcontext": nullcontext}
        exec(compile(ast.Module(body=[method], type_ignores=[]), "catalog", "exec"), scope)
        source = "engineering-workflow:" + "a" * 64
        entry = {"source": source, "prefix": "demo", "ontology_name": "Demo", "ontology_id": "demo_1",
                 "validation": {"rdf_format": "turtle"}, "lifecycle_status": "draft"}
        fake = SimpleNamespace(_transition_lock=threading.RLock(), _postgres_enabled=False,
            _validate_registration=lambda **kw: (kw["prefix"], kw["filename"], {"rdf_format": "xml"}),
            list=lambda: [entry], read_artifact=lambda oid: ({}, b"rdf"),
            _register=lambda **kwargs: self.fail("Retry created another registration"))
        class Graph:
            def parse(self, *, data, format): self.data = data; return self
        rdf = ModuleType("rdflib.compare")
        rdf.isomorphic = lambda a, b: a.data == b.data
        scope["Graph"] = Graph
        with patch.dict(sys.modules, {"rdflib": ModuleType("rdflib"), "rdflib.compare": rdf}):
            result = scope["register"](fake, source=source, prefix="demo", ontology_name="Demo", filename="demo.rdf", content=b"rdf")
            self.assertIs(result, entry)
            with self.assertRaises(ValueError):
                scope["register"](fake, source=source, prefix="demo", ontology_name="Demo", filename="demo.rdf", content=b"different")
            entry["lifecycle_status"] = "retired"
            with self.assertRaises(ValueError):
                scope["register"](fake, source=source, prefix="demo", ontology_name="Demo", filename="demo.rdf", content=b"rdf")


if __name__ == "__main__":
    unittest.main()
