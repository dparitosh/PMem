import ast
import asyncio
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace, ModuleType
import sys
import unittest
from unittest.mock import patch
from backend.agentic_service.workflow_control import checkpoint, WorkflowCancelled

ROOT = Path(__file__).resolve().parents[1]


def extract(relative, name, scope):
    tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
    node = next(n for n in tree.body if getattr(n, "name", None) == name)
    node.decorator_list = []
    exec(compile(ast.Module(body=[node], type_ignores=[]), relative, "exec"), scope)
    return scope[name]


class Failure(Exception):
    def __init__(self, status, detail): self.status_code, self.detail = status, detail


class AgentCatalogControls(unittest.IsolatedAsyncioTestCase):
    async def test_cancel_stops_at_checkpoint(self):
        with self.assertRaises(WorkflowCancelled):
            await checkpoint(SimpleNamespace(get=lambda key: {"action": "cancel"}), "run_1")

    async def test_pause_waits_for_resume(self):
        states = iter([{"action": "pause"}, {"action": "resume"}])
        await checkpoint(SimpleNamespace(get=lambda key: next(states)), "run_1")

    def test_catalog_write_verifies_central_authority(self):
        module = ModuleType("backend.depo_platform.credentials")
        calls = []
        module.uses_postgres = lambda: True
        module.verify_key = lambda profile, token: calls.append((profile, token))
        fn = extract("data_catalog_service/router.py", "_internal", {})
        with patch.dict(sys.modules, {"backend.depo_platform.credentials": module}):
            fn("central-key")
            self.assertEqual(calls, [("CATALOG_SERVICE_TOKEN", "central-key")])
            def rejected(*args): raise Failure(403, "revoked")
            module.verify_key = rejected
            with self.assertRaises(Failure): fn("old-env-key")

    def test_all_catalog_reads_require_auth(self):
        tree = ast.parse((ROOT / "data_catalog_service/router.py").read_text(encoding="utf-8"))
        gets = [n for n in tree.body if isinstance(n, ast.FunctionDef) and any(
            isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr == "get" for d in n.decorator_list)]
        self.assertGreaterEqual(len(gets), 5)
        for fn in gets:
            self.assertTrue(any(isinstance(n, ast.Name) and n.id == "graph_read_identity" for d in fn.decorator_list for n in ast.walk(d)))

    def test_control_rejects_invalid_terminal_and_reversal(self):
        auth = ModuleType("backend.depo_platform.authorization")
        auth.service_write_identity = lambda *args, **kw: "supervisor"
        record = {"status": "running", "deadline_at": (datetime.now(timezone.utc) + timedelta(seconds=60)).isoformat()}
        writes = []
        controls = SimpleNamespace(get=lambda key: {"action": "cancel"}, put=lambda *args: writes.append(args), advisory_lock=lambda key: nullcontext(True))
        scope = {"Any": object, "Request": object, "HTTPException": Failure, "datetime": datetime, "timezone": timezone,
                 "workflow_store": SimpleNamespace(get=lambda key: record), "workflow_controls": controls, "_now": lambda: "now"}
        fn = extract("agentic_service/router.py", "control_workflow", scope)
        with patch.dict(sys.modules, {"backend.depo_platform.authorization": auth}):
            for action in [[], "resume", "invalid"]:
                with self.assertRaises(Failure): fn("run_1", {"action": action}, object())
            record["status"] = "completed"
            with self.assertRaises(Failure): fn("run_1", {"action": "cancel"}, object())
        self.assertEqual(writes, [])

    def test_owl_agent_uses_detected_turtle_serialization(self):
        from tempfile import TemporaryDirectory
        native = ModuleType("backend.ontology_service.catalog")
        native.OntologyCatalog = SimpleNamespace(_parse_ontology=lambda content, name: {"rdf_format": "turtle"})
        native.validate_rdf_input = lambda *args: None
        parsed = []
        class Graph:
            def parse(self, **kwargs): parsed.append(kwargs); return self
            def __len__(self): return 1
        fn = extract("agentic_service/ontology_orchestrator.py", "_load", {"Graph": Graph, "Path": Path, "os": __import__("os")})
        with TemporaryDirectory() as temp, patch.dict(sys.modules, {"backend.ontology_service.catalog": native}):
            path = Path(temp) / "demo.owl"; path.write_text("turtle")
            fn(path)
        self.assertEqual(parsed[0]["format"], "turtle")

    def test_native_catalog_resolution(self):
        from tempfile import TemporaryDirectory
        legacy = ModuleType("backend.Services.ontology_upload_manager")
        legacy.OntologyUploadManager = SimpleNamespace(get_ontology=lambda key: {"status": "error"})
        native = ModuleType("backend.ontology_service.catalog")
        with TemporaryDirectory() as temp:
            root = Path(temp); path = root / "demo_1" / "demo.ttl"; path.parent.mkdir(); path.write_text("rdf")
            native.catalog = SimpleNamespace(root=root, get=lambda key: {"artifact_path": str(path)})
            fn = extract("agentic_service/ontology_orchestrator.py", "_resolve_ontology_path", {"Path": Path})
            with patch.dict(sys.modules, {"backend.Services.ontology_upload_manager": legacy, "backend.ontology_service.catalog": native}):
                self.assertEqual(fn("", "demo_1"), str(path.resolve()))


if __name__ == "__main__": unittest.main()
