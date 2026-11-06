"""Explicit operator action: register a schema-set draft, never approve/publish."""
import argparse
import hashlib
import json
from pathlib import Path
from dotenv import load_dotenv


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("schemas", type=Path)
    args = parser.parse_args()
    load_dotenv(".env.local")
    from backend.qif.ontology_builder import inspect_schema_set, build_ontology_turtle
    from backend.ontology_service.catalog import OntologyCatalog
    from backend.artifact_store import ArtifactStore
    from rdflib import Graph
    from rdflib.namespace import RDF, OWL
    paths = sorted(args.schemas.glob("*.xsd"))
    if not paths:
        raise ValueError("No schemas supplied")
    digest = hashlib.sha256(b"".join(p.name.encode() + b"\0" + p.read_bytes() for p in paths)).hexdigest()
    catalog = OntologyCatalog()
    for existing in catalog.list():
        if existing.get("schema_set_digest") == digest:
            print(json.dumps({"ontology_id": existing["ontology_id"], "status": "existing_draft"}))
            return
    content, report = build_ontology_turtle(inspect_schema_set(paths), "plmxml")
    graph = Graph().parse(data=content, format="turtle")
    counts = {"triples": len(graph), "classes": len(set(graph.subjects(RDF.type, OWL.Class))),
              "object_properties": len(set(graph.subjects(RDF.type, OWL.ObjectProperty))),
              "datatype_properties": len(set(graph.subjects(RDF.type, OWL.DatatypeProperty)))}
    store = ArtifactStore()
    sources = [store.ingest(path, kind="engineering-schema-source", media_type="application/xml")["artifact_id"] for path in paths]
    profile = {"contract": "schema-analytics-profile-v1", "schema_set_digest": digest,
               "source_artifact_ids": sources, "statistics": counts, "generation_report": report,
               "semantic_completeness": "partial", "publication_status": "not_published"}
    artifact = store.ingest_bytes(json.dumps(profile).encode(), filename="plmxml-schema-analytics.json",
                                  kind="schema-analytics-profile", media_type="application/json")
    record = catalog.register(content=content, filename="plmxml.ttl", ontology_name="PLMXML schema-set draft",
                              prefix="plmxml", source="schema-set-validation",
                              extra_metadata={"schema_set_digest": digest, "analytics_profile_artifact_id": artifact["artifact_id"],
                                              "source_artifact_ids": sources, "semantic_completeness": "partial", "statistics": counts})
    print(json.dumps({"ontology_id": record["ontology_id"], "lifecycle_status": record["lifecycle_status"],
                      "analytics_profile": artifact["artifact_id"], "statistics": counts}))


if __name__ == "__main__":
    main()
