"""Exercise retained shape resolution and bounded semantic export."""
import ast
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[2]

def load_function(path, name, scope):
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    function.decorator_list = []
    class StripImports(ast.NodeTransformer):
        def visit_Import(self, node): return None
        def visit_ImportFrom(self, node): return None
    module = StripImports().visit(ast.Module(body=[function], type_ignores=[]))
    exec(compile(ast.fix_missing_locations(module), path, "exec"), scope)
    return scope[name]

class HTTPError(Exception):
    def __init__(self, status, detail): self.status_code = status; self.detail = detail

class ArtifactBoundaries(unittest.TestCase):
    def test_shacl_export_resolves_content_not_metadata(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "content"; path.write_bytes(b"@prefix sh: <http://www.w3.org/ns/shacl#> .")
            class Store:
                def resolve(self, artifact_id): return {"artifact_id": artifact_id}, path
            class Reasoning:
                @staticmethod
                def semantic_context(identifier): return {"meta": {"engineering_artifacts": {"shacl": "sha256:test"}}}
            scope = {"Response": lambda content, **kw: content, "HTTPException": HTTPError,
                "OntologyReasoningService": Reasoning, "ArtifactStore": Store, "ontology_upload_limit": lambda: 200, "Path": Path}
            export = load_function("backend/ingestion_service/api/ontology_browser.py", "export_ontology", scope)
            self.assertEqual(export("version", "shacl"), path.read_bytes())
            scope["ontology_upload_limit"] = lambda: 2
            with self.assertRaises(HTTPError) as caught: export("version", "shacl")
            self.assertEqual(caught.exception.status_code, 413)

    def test_native_validation_retained_shape_identity(self):
        with TemporaryDirectory() as directory:
            ontology = Path(directory) / "ontology.ttl"; ontology.write_bytes(b"ontology")
            shapes = Path(directory) / "content"; shapes.write_bytes(b"shapes")
            class Store:
                def resolve(self, identifier): return {}, shapes
            class Catalog:
                @staticmethod
                def _parse_ontology(content, filename): return {"rdf_format": "turtle"}
            class Graph:
                def parse(self, **kw): return self
                def subjects(self, *args): return []
                def subject_objects(self, *args): return []
            class OWL: Nothing = "nothing"; disjointWith = "disjoint"
            class RDF: type = "type"
            scope = {"Path": Path, "OntologyCatalog": Catalog, "Graph": Graph, "OWL": OWL, "RDF": RDF,
                "ArtifactStore": Store, "ontology_upload_limit": lambda: 200,
                "validate": lambda *a, **kw: (True, None, "conforms")}
            validate = load_function("backend/Services/workflow_validation.py", "validate_semantic_artifact", scope)
            result = validate({"artifact_path": str(ontology), "engineering_artifacts": {"shacl": "sha256:test"}})
            self.assertEqual(result["shacl"]["shape_source"], "retained")
            self.assertEqual(result["shacl"]["shape_artifact_id"], "sha256:test")

if __name__ == "__main__": unittest.main()
