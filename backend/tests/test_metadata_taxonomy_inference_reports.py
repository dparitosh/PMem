from pathlib import Path

import pytest
from rdflib import Graph, Namespace, RDF
from rdflib.namespace import OWL, RDFS, XSD

from backend.routes import metadata_registry_routes
from backend.Services.ontology_quality_guard import assess_ontology_quality
from backend.Services.ontology_reasoning_service import OntologyReasoningService
from backend.Services.ontology_taxonomy_service import OntologyTaxonomyService
from backend.Services.ontology_upload_manager import OntologyUploadManager
from backend.Services.semantic_taxonomy_service import SemanticTaxonomyService, normalize_skos_payload
from backend.Services.shacl_service import ShaclValidationService, validate as pyshacl_validate
from backend.Services.swrl_reasoning_service import ApplicationRuleExecutor, SemanticFact, SwrlRuleService
from backend.Services.workflow_artifact_service import WorkflowArtifactService
from backend.Services.xsd_relational_report import build_xsd_relational_report


class _RecordingGraph:
    def __init__(self):
        self.calls = []

    def query(self, cypher, params=None):
        self.calls.append((cypher, params or {}))
        if "RETURN properties(a) AS asset" in cypher:
            payload = dict((params or {}).get("updates") or params or {})
            return [{"asset": {"asset_id": (params or {}).get("asset_id"), **payload}}]
        return []


def test_metadata_create_uses_unique_create_and_patch_is_partial(monkeypatch):
    recorder = _RecordingGraph()
    monkeypatch.setattr(metadata_registry_routes, "graph", recorder)

    metadata_registry_routes.create_metadata_asset(
        metadata_registry_routes.MetadataAssetRequest(asset_id="asset-1", name="Pump")
    )
    metadata_registry_routes.update_metadata_asset(
        "asset-1", metadata_registry_routes.MetadataAssetUpdateRequest(name="Pump v2")
    )

    create_cypher = next(cypher for cypher, _ in recorder.calls if "e.action = 'created'" in cypher)
    patch_call = next((cypher, params) for cypher, params in recorder.calls if "a += $updates" in cypher)
    assert "CREATE (a:MetadataAsset" in create_cypher
    assert "MERGE (a:MetadataAsset" not in create_cypher
    assert patch_call[1]["updates"] == {"name": "Pump v2"}


def test_metadata_dates_and_lifecycle_values_are_validated():
    with pytest.raises(ValueError):
        metadata_registry_routes.MetadataAssetRequest(
            name="Invalid", effective_from="2026-02-02", effective_to="2026-01-01"
        )
    with pytest.raises(ValueError):
        metadata_registry_routes.LifecycleTransitionRequest(status="anything-goes")


def test_ontology_registry_uses_unique_ids_and_contains_uploaded_filename(monkeypatch, tmp_path):
    monkeypatch.setattr(OntologyUploadManager, "ONTOLOGY_STORAGE_DIR", tmp_path / "registry")
    OntologyUploadManager._invalidate_list_cache()

    first = OntologyUploadManager.save_ontology_file(
        b"one", "../../first.ttl", "First", "Demo", "other", "as_is"
    )
    second = OntologyUploadManager.save_ontology_file(
        b"two", "second.ttl", "Second", "Demo", "other", "as_is"
    )

    assert first["status"] == second["status"] == "success"
    assert first["ontology_id"] != second["ontology_id"]
    first_path = Path(first["storage_path"]).resolve()
    assert (tmp_path / "registry").resolve() in first_path.parents
    assert first_path.name == "first.ttl"
    assert second["replaces"] == first["ontology_id"]


def test_skos_rejects_dropped_duplicates_and_cross_scheme_concepts():
    with pytest.raises(ValueError, match="requires concept_id"):
        normalize_skos_payload({"scheme": {"id": "s"}, "concepts": [{"id": "missing-label"}]})
    with pytest.raises(ValueError, match="Duplicate"):
        normalize_skos_payload({
            "scheme": {"id": "s"},
            "concepts": [{"id": "same", "label": "One"}, {"id": "same", "label": "Two"}],
        })
    with pytest.raises(ValueError, match="expected s"):
        normalize_skos_payload({
            "scheme": {"id": "s"},
            "concepts": [{"id": "other", "label": "Other", "scheme_id": "different"}],
        })


def test_skos_depth_boundary_has_no_dangling_edges():
    _, concepts = normalize_skos_payload({
        "scheme": {"id": "s"},
        "concepts": [
            {"id": "root", "label": "Root", "narrower": ["child"]},
            {"id": "child", "label": "Child", "narrower": ["grand"]},
            {"id": "grand", "label": "Grand"},
        ],
    })
    result = SemanticTaxonomyService.traverse(concepts, "root", "narrower", 1)
    node_ids = {item["concept_id"] for item in result["nodes"]}
    assert all(edge["source"] in node_ids and edge["target"] in node_ids for edge in result["edges"])


def test_xml_taxonomy_truncation_filters_dangling_edges(tmp_path):
    source = tmp_path / "large.xml"
    source.write_text(
        '<root name="Root">' + ''.join(f'<item name="N{i}"/>' for i in range(1100)) + '</root>',
        encoding="utf-8",
    )
    result = OntologyTaxonomyService._xml_terms(source, "p")
    node_ids = {item["term_id"] for item in result["nodes"]}
    assert result["truncated"] is True
    assert all(edge["source_term"] in node_ids and edge["target_term"] in node_ids for edge in result["edges"])


def test_disabled_rule_does_not_execute():
    rule = SwrlRuleService.parse_rule({
        "id": "disabled", "enabled": False, "expression": "ex:A(?x) -> ex:B(?x)"
    })
    result = ApplicationRuleExecutor.execute(
        rule, [SemanticFact("item", "rdf:type", "ex:A")], "exec"
    )
    assert result["status"] == "disabled"
    assert result["inferred_facts"] == []


def test_reasoning_preview_uses_full_type_closure_and_separates_constraints(monkeypatch):
    reasoning = {
        "ontology_id": "o",
        "prefix": "o",
        "classes": [{"iri": key, "label": key} for key in ("A", "B", "C")],
        "subclass_edges": [{"source": "A", "target": "B"}, {"source": "B", "target": "C"}],
        "object_properties": [{"iri": "p", "label": "p", "domain": [{"iri": "A"}], "range": [{"iri": "B"}]}],
        "datatype_properties": [],
        "individuals": [{"iri": "i", "types": [{"iri": "A"}]}],
    }
    monkeypatch.setattr(
        OntologyReasoningService,
        "semantic_context",
        classmethod(lambda cls, _identifier: {"meta": {}, "file_path": "missing", "prefix": "o"}),
    )
    monkeypatch.setattr(
        OntologyReasoningService,
        "inspect_context",
        classmethod(lambda cls, _context: reasoning),
    )
    result = OntologyReasoningService.preview_inferences("o", {
        "rules": {
            "transitive_subclass": True,
            "domain_range_typing": True,
            "equivalence": False,
            "disjointness": False,
            "individual_type_closure": True,
        }
    })
    individual_types = {
        row["object"] for row in result["inferences"]
        if row["rule"] == "individual_type_closure"
    }
    assert individual_types == {"B", "C"}
    assert all(row["predicate"] not in {"rdfs:domain", "rdfs:range"} for row in result["inferences"])
    assert len(result["constraints"]) == 2


def test_xsd_report_honors_optional_attributes_and_nested_type_ownership(tmp_path):
    path = tmp_path / "model.xsd"
    path.write_text(
        '''<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
        <xs:complexType name="Outer"><xs:sequence><xs:element name="nested"><xs:complexType>
          <xs:sequence><xs:element name="inner" type="xs:string"/></xs:sequence>
        </xs:complexType></xs:element></xs:sequence>
        <xs:attribute name="note" type="xs:string" use="optional"/></xs:complexType>
        </xs:schema>''',
        encoding="utf-8",
    )
    report = build_xsd_relational_report(path)
    columns = {item["name"]: item for item in report["columns"]}
    assert columns["note"]["required"] is False
    assert "inner" not in columns


def test_quality_report_detects_standard_xsd_range_and_turtle_owl(tmp_path):
    path = tmp_path / "quality.owl"
    path.write_text(
        '''@prefix ex: <http://example/> . @prefix owl: <http://www.w3.org/2002/07/owl#> .
        @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
        ex:p a owl:ObjectProperty ; rdfs:range xsd:string .''',
        encoding="utf-8",
    )
    report = assess_ontology_quality(str(path))
    assert report.object_property_xsd_like_range == 1


@pytest.mark.skipif(pyshacl_validate is None, reason="pyshacl is not installed")
def test_shacl_validation_uses_default_shapes_when_none_are_supplied():
    ex = Namespace("http://example/")
    graph = Graph()
    graph.add((ex.MissingLabel, RDF.type, OWL.Class))

    report = ShaclValidationService().validate_graph(graph)

    assert report["shape_summary"]["node_shapes"] > 0
    assert report["conforms"] is False


def test_artifact_manifests_are_private_atomic_and_task_paths_do_not_collide(monkeypatch, tmp_path):
    monkeypatch.setattr(WorkflowArtifactService, "ARTIFACT_ROOT", tmp_path)
    WorkflowArtifactService.write_json("task/a", "reports", "one.json", {"ok": True}, "report")
    WorkflowArtifactService.write_json("task_a", "reports", "two.json", {"ok": True}, "report")

    first = WorkflowArtifactService.get_manifest("task/a")
    second = WorkflowArtifactService.get_manifest("task_a")
    assert WorkflowArtifactService.task_dir("task/a") != WorkflowArtifactService.task_dir("task_a")
    assert all("absolute_path" not in item for item in first["artifacts"] + second["artifacts"])
    assert not list(tmp_path.rglob("*.tmp"))
