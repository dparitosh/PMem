from pathlib import Path
import pytest

from backend.ceim.contract import contract
from backend.ceim.plmxml_adapter import plmxml_to_ceim_batch
from backend.ceim_service.app import app
from fastapi.testclient import TestClient


FIXTURE = Path("D:/Githuv_repo/PLMXML/EBOM-Export/Motor_EBOM.xml")


def test_induction_motor_fragment_references_are_preserved():
    source = Path("D:/Githuv_repo/PLMXML/003257_InductionMotor.xml")
    if not source.is_file():
        pytest.skip("Customer fixture not installed")
    batch = plmxml_to_ceim_batch(source.read_bytes())
    assert len(batch["entities"]) == 1980
    # Includes parser relationships plus declared ProductView root/product
    # reference fields that the former generic parser did not emit.
    assert len(batch["relationships"]) == 1688
    assert batch["source_summary"]["unmapped_relationships"] == 0
    resources = {entity["id"] for entity in batch["entities"] if entity["provenance"]["source_type"] in {"Terminal", "ConnectionRevision", "GDE"}}
    assert len(resources) == 300
    assert all(edge["relationship"] == "TRACE_TO" for edge in batch["relationships"] if edge["target_id"] in resources)
    ids = {entity["id"] for entity in batch["entities"]}
    assert all(edge["source_id"] in ids and edge["target_id"] in ids for edge in batch["relationships"])
    assert {edge["provenance"]["source_key"] for edge in batch["relationships"]} >= {"part_ref", "parent_ref", "root_refs", "product_ref"}
    assert contract.validate_projection(entities=batch["entities"], relationships=batch["relationships"])["conforms"]


def test_teamcenter_plmxml_normalizes_to_a_valid_ceim_batch():
    if not FIXTURE.is_file():
        pytest.skip("PLMXML fixture not installed")
    batch = plmxml_to_ceim_batch(FIXTURE.read_bytes())
    assert batch["standard"] == "plmxml"
    assert batch["source_summary"]["parts"] > 0
    assert batch["entities"]
    assert batch["relationships"]
    report = contract.validate_projection(entities=batch["entities"], relationships=batch["relationships"])
    assert report["conforms"] is True


def test_teamcenter_plmxml_adapter_is_registered_in_the_openapi_service():
    if not FIXTURE.is_file():
        pytest.skip("PLMXML fixture not installed")
    response = TestClient(app).post(
        "/api/v1/ceim/adapters/plmxml/normalize",
        files={"file": (FIXTURE.name, FIXTURE.read_bytes(), "application/xml")},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["standard"] == "plmxml"
    assert payload["representation"] == "normalized-ceim-v1"
    assert payload["source_artifact_id"].startswith("sha256:")


def test_declared_requirement_specs_keep_revision_and_trace_carriers():
    content=b"""<PLMXML xmlns='http://www.plmxml.org/Schemas/PLMXMLSchema'>
    <Product id='master' name='Motor requirement specification' subType='RequirementSpec' productId='R-1'/>
    <ProductRevision id='rev' name='Motor requirement specification A' subType='RequirementSpec Revision' masterRef='#master' revision='A'/>
    <Product id='other' name='Subsystem requirement specification' subType='RequirementSpec'/>
    <GeneralRelation id='trace' subType='FND_TraceLink' relatedRefs='#rev #other'/>
    </PLMXML>"""
    result=plmxml_to_ceim_batch(content)
    entities={row['id']:row for row in result['entities']}
    assert entities['plmxml:master']['ceim_type']=='Requirement'
    assert entities['plmxml:rev']['properties']['revision']=='A'
    assert entities['plmxml:trace']['ceim_type']=='Resource'
    links={(row['source_id'],row['target_id'],row['relationship']) for row in result['relationships']}
    assert ('plmxml:rev','plmxml:master','TRACE_TO') in links
    assert ('plmxml:trace','plmxml:rev','TRACE_TO') in links
    assert ('plmxml:trace','plmxml:other','TRACE_TO') in links
    assert not any(row['relationship']=='SATISFIES' for row in result['relationships'])


def test_manufacturing_occurrence_chain_retains_declared_process_and_part_references():
    source=b"""<PLMXML xmlns='http://www.plmxml.org/Schemas/PLMXMLSchema'>
    <Product id='part' name='Motor shaft'/>
    <Process id='process' name='Finish grinding'/>
    <ProcessRevision id='revision' name='Finish grinding A' masterRef='#process' revision='A'/>
    <ProcessOccurrence id='operation' name='Grinding operation' instancedRef='#revision' occurrenceRefs='consumed'/>
    <Occurrence id='consumed' subType='MEConsumed' instancedRef='#part' parentRef='#operation'/>
    </PLMXML>"""
    batch=plmxml_to_ceim_batch(source)
    rows={row['id']:row for row in batch['entities']}
    assert rows['plmxml:operation']['ceim_type']=='Process'
    assert rows['plmxml:consumed']['ceim_type']=='Resource'
    links={(row['source_id'],row['target_id']) for row in batch['relationships']}
    assert ('plmxml:operation','plmxml:revision') in links
    assert ('plmxml:revision','plmxml:process') in links
    assert ('plmxml:operation','plmxml:consumed') in links
    assert ('plmxml:consumed','plmxml:part') in links
    assert not any(row['relationship']=='CONSUMES' for row in batch['relationships'])


def test_declared_external_reference_is_not_silently_counted_as_complete():
    batch=plmxml_to_ceim_batch(b'<PLMXML xmlns="http://www.plmxml.org/Schemas/PLMXMLSchema"><ProductRevision id="r" masterRef="other.xml#id1"/></PLMXML>')
    assert batch['mapping_diagnostics']['status']=='review_required'
    assert batch['source_summary']['unresolved_references'] > 0
    assert any(row['target_id']=='other.xml#id1' for row in batch['mapping_diagnostics']['unresolved_reference_samples'])


def test_duplicate_identity_in_unmapped_plmxml_content_cannot_shadow_a_product():
    with pytest.raises(ValueError,match='duplicate identifier'):
        plmxml_to_ceim_batch(b'<PLMXML xmlns="http://www.plmxml.org/Schemas/PLMXMLSchema"><Product id="p"/><VendorRecord id="p"/></PLMXML>')


def test_work_area_chain_preserves_resources_and_resolves_declared_manufacturing_links():
    source=b'<PLMXML xmlns="http://www.plmxml.org/Schemas/PLMXMLSchema"><ProcessOccurrence id="op" occurrenceRefs="wa"/><WorkAreaOccurrence id="wa" parentRef="#op" instancedRef="#rev" instanceRefs="#i"/><WorkArea id="master" name="Boring station"/><WorkAreaRevision id="rev" masterRef="#master" revision="A"/><WorkAreaInstance id="i" partRef="#view"/><PlantRevisionView id="view" revisionRef="#rev"/></PLMXML>'
    batch=plmxml_to_ceim_batch(source)
    entities={row['id']:row for row in batch['entities']}
    assert set(entities)=={'plmxml:op','plmxml:wa','plmxml:rev','plmxml:master','plmxml:i','plmxml:view'}
    assert all(entities['plmxml:'+key]['ceim_type']=='Resource' for key in ['wa','rev','master','i','view'])
    assert batch['source_summary']['unresolved_references']==0
    assert batch['mapping_diagnostics']['status']=='complete_for_declared_profile'
    links={(row['source_id'],row['target_id']) for row in batch['relationships']}
    assert {('plmxml:op','plmxml:wa'),('plmxml:wa','plmxml:rev'),('plmxml:wa','plmxml:i'),('plmxml:i','plmxml:view'),('plmxml:view','plmxml:rev'),('plmxml:rev','plmxml:master')} <= links
    assert contract.validate_projection(entities=batch['entities'],relationships=batch['relationships'])['conforms']
