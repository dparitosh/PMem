"""Shared workflow capability registry for API and admin surfaces."""

from __future__ import annotations

from typing import Any, Dict, List


WORKFLOW_REGISTRY: List[Dict[str, Any]] = [
    {
        "id": "instance.import",
        "label": "Import instance graph",
        "category": "Import",
        "execution_surface": "upload",
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
        "execution_surface": "upload",
        "inputs": "EXPRESS, OWL, RDF, TTL, XSD, XMI, MDXML",
        "outputs": "Ontology preview, prefix metadata, schema classes",
        "status": "existing_upload_pipeline",
        "execution": "File upload",
        "prerequisite": "Choose an ontology/schema file",
        "writes_to_neo4j": False,
        "retains_artifacts": True,
    },
    {
        "id": "document.unstructured",
        "label": "Unstructured document pipeline",
        "category": "AI Ingestion",
        "execution_surface": "upload",
        "inputs": "PDF, Word, PowerPoint",
        "outputs": "Document chunks, embedding index, GraphRAG retrieval context",
        "status": "existing_upload_pipeline",
        "execution": "Document upload",
        "prerequisite": "Choose one or more documents",
        "writes_to_neo4j": True,
        "retains_artifacts": True,
    },    {
        "id": "instance.link",
        "label": "Link instances to ontology",
        "category": "Mapping",
        "execution_surface": "artifact",
        "inputs": "Existing graph plus ontology",
        "outputs": "Mapping candidates, applied ontology links, confidence report",
        "status": "artifact_report",
        "execution": "Artifact workflow",
        "prerequisite": "Run an import first, then select ontology",
        "writes_to_neo4j": True,
        "retains_artifacts": True,
    },
    {
        "id": "ontology.merge",
        "label": "Merge ontologies",
        "category": "Ontology",
        "execution_surface": "artifact",
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
        "execution_surface": "artifact",
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
        "execution_surface": "artifact",
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
        "execution_surface": "artifact",
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
        "execution_surface": "artifact",
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


def get_workflow_by_id(workflow_id: str) -> Dict[str, Any] | None:
    lookup = str(workflow_id or "").strip()
    if not lookup:
        return None
    for workflow in WORKFLOW_REGISTRY:
        if workflow["id"] == lookup:
            return dict(workflow)
    return None


def get_workflow_map() -> Dict[str, Dict[str, Any]]:
    return {workflow["id"]: dict(workflow) for workflow in WORKFLOW_REGISTRY}


def get_workflow_options() -> List[Dict[str, str]]:
    return [
        {
            "id": workflow["id"],
            "label": workflow["label"],
            "title": workflow["label"],
            "category": workflow["category"],
            "execution_surface": workflow.get("execution_surface", "artifact"),
            "status": workflow["status"],
            "execution": workflow["execution"],
            "prerequisite": workflow["prerequisite"],
        }
        for workflow in WORKFLOW_REGISTRY
    ]
