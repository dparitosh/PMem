from pathlib import Path

from backend.ontology_service.catalog import OntologyCatalog
from backend.ontology_service.merge_service import GovernedMergeService


class IntelligenceStub:
    def create_version(self, **kwargs):
        return {"version_id": "approved-version", **kwargs}


def test_approved_merge_persists_provenance_and_version(tmp_path: Path):
    catalog = OntologyCatalog(root=tmp_path / "catalog")
    first = catalog.register(content=b"@prefix ex: <https://example.test/> . ex:A ex:label \"A\" .", filename="one.ttl", ontology_name="One", prefix="one")
    second = catalog.register(content=b"@prefix ex: <https://example.test/> . ex:B ex:label \"B\" .", filename="two.ttl", ontology_name="Two", prefix="two")
    service = GovernedMergeService(catalog, IntelligenceStub(), catalog.root)

    preview = service.preview({"source_ontology_ids": [first["ontology_id"], second["ontology_id"]], "ontology_name": "Combined", "prefix": "combined"})
    merged = service.apply(preview["preview_id"], "release-manager")

    assert merged["status"] == "merged"
    assert merged["ontology"]["provenance"]["source_ontology_ids"] == [first["ontology_id"], second["ontology_id"]]
    assert merged["version"]["version_id"] == "approved-version"
