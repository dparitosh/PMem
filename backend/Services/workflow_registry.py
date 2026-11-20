"""Shared workflow capability registry for API and admin surfaces."""

from __future__ import annotations

from typing import Any, Dict, List


WORKFLOW_REGISTRY: List[Dict[str, Any]] = [
    {
        "id": "instance.import",
        "family": "instance.import",
        "activity": "ingestion",
        "adapter": None,
        "label": "Import instance graph",
        "category": "Import",
        "execution_surface": "upload",
        "inputs": "STEP, STPX, CSV, Excel, JSON, XML, PLMXML, ReqIF, 3DXML",
        "outputs": "Instance graph, preview rows, entity and relationship counts",
        "status": "existing_import_pipeline",
        "execution": "File upload",
        "prerequisite": "Choose one or more files",
        "writes_to_neo4j": True,
        "retains_artifacts": True,
    },
    {
        "id": "ontology.create",
        "family": "ontology.create",
        "activity": "ingestion",
        "adapter": None,
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
        "family": "document.unstructured",
        "activity": "ingestion",
        "adapter": None,
        "label": "Document processing workflow",
        "category": "AI Ingestion",
        "execution_surface": "upload",
        "inputs": "PDF, Word, PowerPoint, Text, Markdown, HTML",
        "outputs": "Document chunks, embedding index, GraphRAG retrieval context",
        "status": "existing_upload_pipeline",
        "execution": "Document upload",
        "prerequisite": "Choose one or more documents",
        "writes_to_neo4j": True,
        "retains_artifacts": True,
    },
    {
        "id": "architecture.archimate",
        "family": "instance.import",
        "activity": "ingestion",
        "adapter": "archimate",
        "label": "Import ArchiMate process model",
        "category": "Architecture",
        "execution_surface": "upload",
        "inputs": "ArchiMate Model Exchange XML",
        "outputs": "Architecture/process graph, typed relationships, process-reference context",
        "status": "existing_import_pipeline",
        "execution": "File upload",
        "prerequisite": "Choose an ArchiMate Model Exchange XML file",
        "writes_to_neo4j": True,
        "retains_artifacts": True,
    },
    {
        "id": "instance.link",
        "family": "instance.import",
        "activity": "alignment",
        "adapter": None,
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
        "family": "ontology.create",
        "activity": "merge",
        "adapter": None,
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
        "family": "ontology.create",
        "activity": "validation",
        "adapter": None,
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
        "family": "ontology.create",
        "activity": "dictionary",
        "adapter": None,
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
        "family": "ontology.create",
        "activity": "taxonomy",
        "adapter": None,
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
        "family": "ontology.create",
        "activity": "export",
        "adapter": None,
        "label": "Export graph chunks",
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


def get_workflow_options() -> List[Dict[str, Any]]:
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
            "family": workflow["family"],
            "activity": workflow["activity"],
            "adapter": workflow["adapter"],
            "inputs": workflow["inputs"],
            "outputs": workflow["outputs"],
            "writes_to_neo4j": workflow["writes_to_neo4j"],
            "retains_artifacts": workflow["retains_artifacts"],
        }
        for workflow in WORKFLOW_REGISTRY
    ]
