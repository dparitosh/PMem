"""Shared workflow capability registry for API and admin surfaces."""

from __future__ import annotations

from typing import Any, Dict, List


WORKFLOW_REGISTRY: List[Dict[str, Any]] = [
    {
        "id": "instance.import",
        "label": "Import instance graph",
        "category": "Import",
        "inputs": "STEP, STPX, CSV, Excel, JSON, XML, PLMXML, 3DXML",
        "outputs": "Instance graph, preview rows, entity and relationship counts",
        "status": "existing_import_pipeline",
        "execution": "File upload",
        "prerequisite": "Choose one or more files",
        "writes_to_neo4j": True,
        "retains_artifacts": True,
    },
    {
        "id": "ontology.create",
        "label": "Create ontology",
        "category": "Ontology",
        "inputs": "EXPRESS, OWL, RDF, TTL, XSD, XMI, MDXML",
        "outputs": "Ontology preview, prefix metadata, schema classes",
        "status": "existing_upload_pipeline",
        "execution": "File upload",
        "prerequisite": "Choose an ontology/schema file",
        "writes_to_neo4j": False,
        "retains_artifacts": True,
    },
    {
        "id": "instance.link",
        "label": "Link instances to ontology",
        "category": "Mapping",
        "inputs": "Existing graph plus ontology",
        "outputs": "Mapping candidates, confidence report, link review file",
        "status": "artifact_report",
        "execution": "Artifact workflow",
        "prerequisite": "Run an import first, then select ontology",
        "writes_to_neo4j": False,
        "retains_artifacts": True,
    },
    {
        "id": "ontology.merge",
        "label": "Merge ontologies",
        "category": "Ontology",
        "inputs": "Two ontology catalog entries",
        "outputs": "Merge plan, overlap report, addition candidates",
        "status": "artifact_report",
        "execution": "Artifact workflow",
        "prerequisite": "Select source and target ontologies",
        "writes_to_neo4j": False,
        "retains_artifacts": True,
    },
    {
        "id": "ontology.validate",
        "label": "Validate ontology",
        "category": "Quality",
        "inputs": "Ontology catalog entry or file",
        "outputs": "Validation report, finding counts, review suggestions",
        "status": "artifact_report",
        "execution": "Artifact workflow",
        "prerequisite": "Select ontology",
        "writes_to_neo4j": False,
        "retains_artifacts": True,
    },
    {
        "id": "dictionary.generate",
        "label": "Build data dictionary",
        "category": "Governance",
        "inputs": "Ontology, graph, CSV, Excel",
        "outputs": "Data dictionary, term lineage, review queue",
        "status": "artifact_report",
        "execution": "Artifact workflow",
        "prerequisite": "Select ontology",
        "writes_to_neo4j": False,
        "retains_artifacts": True,
    },
    {
        "id": "taxonomy.generate",
        "label": "Build taxonomy",
        "category": "Ontology",
        "inputs": "Ontology or graph",
        "outputs": "Taxonomy tree, synonym set, rejected terms",
        "status": "artifact_report",
        "execution": "Artifact workflow",
        "prerequisite": "Select ontology",
        "writes_to_neo4j": False,
        "retains_artifacts": True,
    },
    {
        "id": "graph.chunk",
        "label": "Chunk and index graph",
        "category": "Graph",
        "inputs": "Ontology or graph",
        "outputs": "Chunk set, index manifest, coverage report",
        "status": "artifact_report",
        "execution": "Artifact workflow",
        "prerequisite": "Select ontology",
        "writes_to_neo4j": False,
        "retains_artifacts": True,
    },
]


def get_workflow_registry() -> List[Dict[str, Any]]:
    return [dict(workflow) for workflow in WORKFLOW_REGISTRY]


def get_workflow_options() -> List[Dict[str, str]]:
    return [
        {
            "id": workflow["id"],
            "status": workflow["status"],
            "execution": workflow["execution"],
            "prerequisite": workflow["prerequisite"],
        }
        for workflow in WORKFLOW_REGISTRY
    ]
