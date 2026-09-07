import json

import pytest

from backend.Services.graph_view_service import GraphViewService
from backend.Services.oslc_query_service import OSLCCondition, OSLCQueryParameters, OSLCQueryService
from backend.Services.oslc_service import OSLCService
from backend.Services.oslc_trs_service import OSLCTRSService
from backend.Services.ontology_upload_manager import OntologyUploadManager


def test_where_parser_keeps_boolean_words_inside_quotes():
    params = OSLCQueryService.parse({"oslc.where": 'title="Motor or Pump" and name="R&D and Validation"'})

    assert [(item.property_name, item.value) for item in params.where] == [
        ("title", "Motor or Pump"),
        ("name", "R&D and Validation"),
    ]


def test_search_terms_parser_supports_oslc_quoted_list():
    params = OSLCQueryService.parse({"oslc.searchTerms": '"REQ","pump assembly"'})

    assert params.search_terms == ["REQ", "pump assembly"]
    cypher, query_params = OSLCService._build_resource_query(params)
    assert "$search_term_0" in cypher
    assert "$search_term_1" in cypher
    assert query_params["search_term_0"] == "req"
    assert query_params["search_term_1"] == "pump assembly"
    assert " OR " in cypher
    assert "AS search_score" in cypher
    assert "ORDER BY search_score DESC" in cypher


def test_numeric_and_negative_type_filters_use_correct_cypher_semantics():
    numeric_params = {}
    numeric = OSLCService._condition_to_cypher(OSLCCondition("count", "<", 2), 0, numeric_params)
    type_params = {}
    negative_type = OSLCService._condition_to_cypher(
        OSLCCondition("rdf:type", "!=", "Requirement"), 0, type_params
    )

    assert numeric == "toFloat(properties(n)[$where_property_0]) < toFloat($where_value_0)"
    assert negative_type.startswith("none(lbl IN labels(n)")


def test_type_ordering_uses_iteration_independent_minimum_label():
    order_by = OSLCService._build_order_by([("rdf:type", "asc")])

    assert "CASE WHEN label_key = '' OR toLower(lbl) < label_key" in order_by


def test_query_rejects_unadvertised_resource_type():
    with pytest.raises(ValueError, match="Unsupported OSLC resource type"):
        OSLCService.query_resources("unknown-domain", OSLCQueryParameters())


def test_service_provider_advertises_am_and_rm_domain_capabilities(monkeypatch):
    monkeypatch.setenv("OSLC_BASE_URL", "https://example.test")

    provider = OSLCService.service_provider()

    domains = {item["id"] for item in provider["domains"]}
    capabilities = {item["resourceType"]: item for item in provider["queryCapabilities"]}
    assert {"oslc_am", "oslc_rm", "oslc_cm", "oslc_qm"}.issubset(domains)
    assert capabilities["architecture-resources"]["resourceTypeUri"] == OSLCService.AM_TYPE_URI
    assert capabilities["requirements"]["resourceTypeUri"] == OSLCService.RM_REQUIREMENT_URI
    assert capabilities["requirement-collections"]["resourceTypeUri"] == OSLCService.RM_COLLECTION_URI
    assert provider["domainResources"]["oslc_rm"]["queryBase"].endswith("/oslc/query/requirements")
    assert capabilities["change-requests"]["resourceTypeUri"] == OSLCService.CM_CHANGE_REQUEST_URI
    assert capabilities["test-results"]["resourceTypeUri"] == OSLCService.QM_TEST_RESULT_URI
    assert set(provider["oslc:domain"]) == {
        "http://open-services.net/ns/am#",
        "http://open-services.net/ns/rm#",
        "http://open-services.net/ns/cm#",
        "http://open-services.net/ns/qm#",
    }
    assert {service["domain"] for service in provider["services"]} == set(provider["oslc:domain"])
    assert all(service["queryCapabilities"] for service in provider["services"])


def test_ontology_domain_query_is_scoped_to_registered_ontology(monkeypatch):
    monkeypatch.setattr(
        OntologyUploadManager,
        "list_ontologies",
        classmethod(lambda cls: {"status": "success", "ontologies": [{
            "ontology_id": "qif-fixed", "prefix": "qif", "ontology_name": "QIF Fixed",
        }]}),
    )

    scope = OSLCService._ontology_domain_scope("ontology:qif-fixed")
    query, query_params = OSLCService._build_resource_query(
        OSLCQueryParameters(), OSLCService.DEFAULT_RESOURCE_TYPE, scope,
    )

    assert scope == {"ontology_id": "qif-fixed", "prefix": "qif"}
    assert "n.ontology_id" in query
    assert query_params["ontology_id"] == "qif-fixed"
    assert query_params["ontology_prefix"] == "qif"


def test_am_and_rm_query_predicates_are_domain_specific():
    requirement_query, _ = OSLCService._build_resource_query(
        OSLCQueryParameters(), OSLCService.RM_REQUIREMENT_TYPE
    )
    collection_query, _ = OSLCService._build_count_query(
        OSLCQueryParameters(), OSLCService.RM_COLLECTION_TYPE
    )
    architecture_query, _ = OSLCService._build_resource_query(
        OSLCQueryParameters(), OSLCService.AM_RESOURCE_TYPE
    )

    assert "'requirementrevision'" in requirement_query
    assert "requirement_specification" in collection_query
    assert "n:ModelElement" in architecture_query
    assert "AND NOT (any(lbl IN labels(n)" in architecture_query


def test_cm_and_qm_query_predicates_are_domain_specific():
    change_query, _ = OSLCService._build_resource_query(OSLCQueryParameters(), OSLCService.CM_CHANGE_REQUEST_TYPE)
    result_query, _ = OSLCService._build_resource_query(OSLCQueryParameters(), OSLCService.QM_TEST_RESULT_TYPE)
    case_query, _ = OSLCService._build_count_query(OSLCQueryParameters(), OSLCService.QM_TEST_CASE_TYPE)

    assert "changerequest" in change_query
    assert "testresult" in result_query
    assert "testcase" in case_query


def test_domain_shapes_publish_am_and_rm_vocabulary(monkeypatch):
    monkeypatch.setenv("OSLC_BASE_URL", "https://example.test")
    monkeypatch.setattr(
        OntologyUploadManager,
        "list_ontologies",
        classmethod(lambda cls: {"status": "success", "ontologies": []}),
    )

    am_shape = OSLCService.resource_shape(OSLCService.AM_RESOURCE_TYPE)
    requirement_shape = OSLCService.resource_shape(OSLCService.RM_REQUIREMENT_TYPE)
    collection_shape = OSLCService.resource_shape(OSLCService.RM_COLLECTION_TYPE)
    listed_ids = {item["shape_id"] for item in OSLCService.list_shapes()["members"]}

    assert am_shape["describes"] == [OSLCService.AM_TYPE_URI]
    assert requirement_shape["describes"] == [OSLCService.RM_REQUIREMENT_URI]
    assert collection_shape["describes"] == [OSLCService.RM_COLLECTION_URI]
    assert {"architecture-resources", "requirements", "requirement-collections"}.issubset(listed_ids)
    assert requirement_shape["properties"][0]["propertyDefinition"] == "http://purl.org/dc/terms/title"


def test_unknown_shape_is_not_resolved_from_an_arbitrary_path(monkeypatch):
    monkeypatch.setattr(
        OntologyUploadManager,
        "list_ontologies",
        classmethod(lambda cls: {"status": "success", "ontologies": []}),
    )
    with pytest.raises(ValueError, match="Unknown OSLC resource shape"):
        OSLCService.resource_shape("not-registered")


@pytest.mark.parametrize(
    ("labels", "properties", "expected"),
    [
        (["Requirement"], {"source_format": "xmi"}, OSLCService.RM_REQUIREMENT_URI),
        (["Specification"], {"source_format": "reqif"}, OSLCService.RM_COLLECTION_URI),
        (["ModelElement"], {"element_type": "Interface"}, OSLCService.AM_TYPE_URI),
    ],
)
def test_resource_domain_type_inference_prioritizes_rm(labels, properties, expected):
    assert OSLCService.resource_domain_types(labels, properties) == [expected]


def test_requirement_detail_exposes_cross_domain_architecture_target(monkeypatch):
    monkeypatch.setenv("OSLC_BASE_URL", "https://example.test")

    payload = OSLCService._resource_detail_payload(
        {
            "element_id": "req-1",
            "labels": ["Requirement"],
            "properties": {"name": "Pump requirement", "semantic_role": "requirement"},
            "outgoing": [
                {
                    "relationshipType": "SATISFIES",
                    "relationshipElementId": "rel-1",
                    "targetElementId": "component-1",
                    "targetLabels": ["Component"],
                    "targetProperties": {"source_format": "xmi"},
                    "targetName": "Pump component",
                }
            ],
        }
    )

    assert payload["rdf:type"] == [OSLCService.RM_REQUIREMENT_URI]
    assert payload["outgoingLinks"][0]["predicate"] == "http://purl.org/dc/terms/relation"
    assert payload["outgoingLinks"][0]["targetRdfTypes"] == [OSLCService.AM_TYPE_URI]


def test_select_projects_structural_fields_and_url_encodes_element_id(monkeypatch):
    monkeypatch.setenv("OSLC_BASE_URL", "https://example.test")
    payload = OSLCService._row_to_resource_payload(
        {
            "element_id": "4:abc/one",
            "labels": ["Requirement", "Individual"],
            "properties": {"name": "Pump requirement", "code": "REQ-1"},
        },
        ["uri", "rdf:type", "title", "code"],
    )

    assert payload["uri"] == "https://example.test/oslc/resources/4%3Aabc%2Fone"
    assert payload["properties"]["uri"] == payload["uri"]
    assert payload["properties"]["rdf:type"] == [OSLCService.RM_REQUIREMENT_URI]
    assert payload["rdf:type"] == [OSLCService.RM_REQUIREMENT_URI]
    assert payload["oslc:instanceShape"].endswith("/oslc/shapes/requirements")
    assert payload["properties"]["title"] == "Pump requirement"
    assert payload["properties"]["code"] == "REQ-1"


def test_invalid_page_size_configuration_uses_safe_default(monkeypatch):
    monkeypatch.setenv("OSLC_MAX_PAGE_SIZE", "not-an-integer")

    assert OSLCService.config().max_page_size == 200


def test_fallback_shape_uses_complete_schema_procedures(monkeypatch):
    calls = []

    def fake_run(cypher, _params=None):
        calls.append(cypher)
        if "labels(n)" in cypher:
            return [{"label": "Part"}, {"label": "Requirement"}]
        return [{"propertyKey": "name"}, {"propertyKey": "catalogue_id"}]

    monkeypatch.setattr(GraphViewService, "_run", staticmethod(fake_run))

    shape = OSLCService._fallback_resource_shape()

    assert shape["describes"] == ["Part", "Requirement"]
    assert shape["properties"] == ["catalogue_id", "name"]
    assert any("UNWIND labels(n)" in call for call in calls)
    assert any("UNWIND keys(n)" in call for call in calls)


def test_shacl_discovery_does_not_scan_working_directory_without_source_path():
    assert OSLCService._discover_shacl_file({}, {}) is None


@pytest.fixture
def isolated_trs(monkeypatch, tmp_path):
    storage_path = tmp_path / "change_log.json"
    monkeypatch.setattr(OSLCTRSService, "_storage_path", classmethod(lambda cls: storage_path))
    monkeypatch.setattr(OSLCTRSService, "base_url", classmethod(lambda cls: "https://current.example"))
    monkeypatch.setattr(OSLCTRSService, "is_enabled", classmethod(lambda cls: True))
    return storage_path


def test_trs_publish_uses_atomic_state_and_oslc_uri(isolated_trs):
    event = OSLCTRSService.publish_event(
        "http://localhost:8000/api/v1/ontology/ont-1",
        "Modification",
        title="Ontology changed",
    )

    state = json.loads(isolated_trs.read_text(encoding="utf-8"))
    assert event["resource_uri"] == "https://current.example/oslc/shapes/ont-1"
    assert state["events"][0]["resource_uri"] == "/oslc/shapes/ont-1"
    assert state["counter"] == 1
    assert not isolated_trs.with_suffix(".lock").exists()
    assert not list(isolated_trs.parent.glob("*.tmp"))


def test_trs_corruption_fails_closed_without_overwrite(isolated_trs):
    isolated_trs.write_text("{broken", encoding="utf-8")

    with pytest.raises(RuntimeError, match="unreadable"):
        OSLCTRSService.publish_event("https://current.example/oslc/shapes/ont-1", "Modification")

    assert isolated_trs.read_text(encoding="utf-8") == "{broken"


def test_trs_change_log_rewrites_old_hosts_and_signals_retention_gap(isolated_trs):
    isolated_trs.write_text(
        json.dumps(
            {
                "counter": 12,
                "first_retained_order": 11,
                "events": [
                    {
                        "event_id": "e11",
                        "order": 11,
                        "event_type": "Modification",
                        "resource_uri": "http://localhost:8000/api/v1/import/status/task-1",
                        "changed_at": "2026-01-01T00:00:00+00:00",
                        "title": "Import",
                        "metadata": {},
                    },
                    {
                        "event_id": "e12",
                        "order": 12,
                        "event_type": "Modification",
                        "resource_uri": "http://old-host/oslc/shapes/ont-2",
                        "changed_at": "2026-01-01T00:00:01+00:00",
                        "title": "Ontology",
                        "metadata": {},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    change_log = OSLCTRSService.change_log(after=5)

    assert change_log["rebase_required"] is True
    assert change_log["events"][0]["resource_uri"].startswith(
        "https://current.example/oslc/query/resources?oslc.where="
    )
    assert change_log["events"][1]["resource_uri"] == "https://current.example/oslc/shapes/ont-2"


def test_trs_base_is_current_graph_snapshot(monkeypatch, isolated_trs):
    isolated_trs.write_text(json.dumps({"counter": 7, "events": []}), encoding="utf-8")
    monkeypatch.setattr(
        OntologyUploadManager,
        "list_ontologies",
        classmethod(lambda cls: {"status": "success", "ontologies": []}),
    )
    monkeypatch.setattr(
        GraphViewService,
        "_run",
        staticmethod(
            lambda _cypher, _params=None: [
                {
                    "element_id": "4:abc/1",
                    "title": "Pump requirement",
                    "labels": ["Requirement"],
                    "domain_properties": {"semantic_role": "requirement"},
                },
                {"element_id": "4:abc/2", "title": "Valve", "labels": ["Part"]},
            ]
        ),
    )

    base = OSLCTRSService.base_resources(limit=10)

    assert base["cutoff_order"] == 7
    assert base["count"] == 2
    assert base["members"][0]["resource_uri"] == "https://current.example/oslc/resources/4%3Aabc%2F1"
    assert base["members"][0]["rdf_types"] == [OSLCService.RM_REQUIREMENT_URI]
    assert base["truncated"] is False


def test_trs_descriptor_includes_rm_domain():
    descriptor = OSLCTRSService.tracked_resource_set()

    assert "oslc_rm" in {item["id"] for item in descriptor["domains"]}
