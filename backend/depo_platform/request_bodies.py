"""Explicit JSON body contracts that retain dictionary semantics for service code.

Strict fields prevent string booleans and accidental scalar-to-container coercion.
Extension fields are retained for the existing governed downstream validators.
"""
from typing import Any, Annotated, Literal
from typing_extensions import TypedDict, Required
from pydantic import ConfigDict, Field

Text = Annotated[str, Field(min_length=1)]

class RequestBody(TypedDict, total=False):
    __pydantic_config__ = ConfigDict(strict=True, extra="allow")

class ApprovalBody(RequestBody, total=False):
    approved_by: str
    approval_token: str

class GenerateOntologyBody(RequestBody, total=False):
    data: dict[str, Any]
    entities: list[dict[str, Any]]
    relationships: list[dict[str, Any]]
    name: str
    base_uri: str

class ValidateGraphBody(RequestBody, total=False):
    __pydantic_config__ = ConfigDict(strict=True, extra="allow", json_schema_extra={"anyOf": [{"required": ["ontology"]}, {"required": ["version_id"]}]})
    data_graph: Required[str]
    ontology: dict[str, Any]
    version_id: Text

class NamespaceBody(RequestBody, total=False):
    prefix: Required[Text]
    uri: Required[Text]

class AlignmentBody(RequestBody, total=False):
    source_uri: Required[Text]
    target_uri: Required[Text]
    predicate: str

class ReasonBody(RequestBody, total=False):
    facts: list[Any]
    rules: list[Any]

class QualityGateBody(RequestBody, total=False):
    entities: list[dict[str, Any]]
    deduplicate: bool
    conflict_property: str | None
    merge_strategy: str

class VersionBody(RequestBody, total=False):
    __pydantic_config__ = ConfigDict(strict=True, extra="allow", json_schema_extra={"anyOf": [{"required": ["ontology"]}, {"required": ["version_id"]}]})
    ontology: dict[str, Any]
    version_id: Text
    label: Required[Text]
    author: str
    description: str

class CompareVersionsBody(RequestBody, total=False):
    older: Required[Text]
    newer: Required[Text]

class GraphAnalyticsBody(RequestBody, total=False):
    graph: dict[str, Any]
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    relationships: list[dict[str, Any]]

class PolicyBody(RequestBody, total=False):
    __pydantic_config__ = ConfigDict(strict=True, extra="allow", json_schema_extra={"anyOf": [{"required": ["policy_id"]}, {"required": ["name"]}]})
    policy_id: Text
    name: Text
    rules: Required[dict[str, Any]]
    active: bool

class EvaluatePoliciesBody(RequestBody, total=False):
    decision: dict[str, Any]
    exception_policy_ids: list[str]

class EntityMapping(RequestBody, total=False):
    source_iri: Required[Text]
    target_iri: Required[Text]

class MergePreviewBody(RequestBody, total=False):
    source_ontology_ids: Required[Annotated[list[Text], Field(min_length=2, max_length=16)]]
    entity_mappings: Annotated[list[EntityMapping], Field(max_length=200)]
    ontology_name: str
    prefix: str
    description: str

class MergeApplyBody(ApprovalBody, total=False):
    publish: bool

class BusinessContextBody(ApprovalBody, total=False):
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    relationships: list[dict[str, Any]]

class TransitionBody(ApprovalBody, total=False):
    target: Required[Text]
    reason: str

class OntologyIdsBody(ApprovalBody, total=False):
    ontology_ids: Required[Annotated[list[Text], Field(min_length=1)]]

class GraphScope(RequestBody, total=False):
    prefix: str
    ontology_prefix: str
    ontology_id: str

class ContextBody(RequestBody, total=False):
    scope: GraphScope
    change_name: str
    part_name: str
    node_id: str
    element_id: str
    top_n: Annotated[int, Field(ge=1, le=500)]

class GraphQLBody(RequestBody, total=False):
    query: Required[Text]
    variables: dict[str, Any] | None
    operationName: str | None

class SparqlBody(RequestBody, total=False):
    ontology_id: Required[Text]
    query: Required[Text]
    limit: Annotated[int, Field(ge=1, le=1000)]

class BrowserSessionBody(RequestBody, total=False):
    include_writes: bool
    include_maintenance: bool

class RotateCredentialBody(RequestBody, total=False):
    key: Required[Text]
    actor: Required[Text]
    expires_at: str | None

class SemanticWorkflowBody(RequestBody, total=False):
    workflow_id: Required[Text]
    payload: dict[str, Any]

class AgentPlanBody(RequestBody, total=False):
    agent_id: Required[Text]
    tool_id: Required[Text]
    approval_required: bool

class WorkflowPlanBody(RequestBody, total=False):
    workflow_id: Required[Text]

class OntologyAgentBody(RequestBody, total=False):
    workflow_id: str
    ontology_path: str
    ontology_id: str
    import_task_id: str
    instance_metadata: dict[str, Any] | None
    artifact_digest: str
    graph_digest: str
    data_source: str
    qif_ontology_id: str
    ap242_ontology_id: str

class WorkflowControlBody(ApprovalBody, total=False):
    action: Required[Text]

class ReconcileWorkflowBody(ApprovalBody, total=False):
    outcome: str
    evidence: str
    result: Any
    executor_stopped: bool

class OslcRetrievalBody(RequestBody, total=False):
    query: Required[Text]
    resource_type: str
    limit: Annotated[int, Field(ge=1, le=1000)]

class VocabularyBody(ApprovalBody, total=False):
    scheme: dict[str, Any]
    scheme_id: str
    version: str
    concepts: Required[list[dict[str, Any]]]
    base_uri: Required[Text]
    steward: Required[Text]
    provenance: Required[dict[str, Any]]

class SemanticReleaseReference(RequestBody, total=False):
    asset_id: Required[Text]
    version: Required[Text]
    lifecycle_status: Required[Text]

class ArtifactReference(RequestBody, total=False):
    artifact_id: Required[Text]

class ProductMetadataBody(RequestBody, total=False):
    name: Required[Text]
    domain: Required[Text]
    owner: Required[Text]
    classification: Required[Text]
    steward: Required[Text]
    lifecycle_state: Required[Text]
    sla: Any
    quality_status: Any
    sources: list[Any]
    ontologies: list[Any]
    semantic_releases: list[SemanticReleaseReference]
    manifest: dict[str, Any]
    product_kind: str
    analytics_readiness: str | dict[str, Any] | None
    product_url: str
    description: str

class ProductPublicationBody(ProductMetadataBody, ApprovalBody, total=False):
    product_id: Required[Text]
    version: Required[Text]
    artifacts: list[ArtifactReference]
    idempotency_key: str

class ReasonApprovalBody(ApprovalBody, total=False):
    reason: str
    idempotency_key: str

class RetentionBody(ReasonApprovalBody, total=False):
    retention_days: Required[Annotated[int, Field(ge=1, le=36500)]]
    legal_hold: bool
    tier: str

class ReconcileProductsBody(ApprovalBody, total=False):
    limit: Annotated[int, Field(ge=1, le=1000)]

class NormalizeRecordBody(RequestBody, total=False):
    standard: Required[Text]
    record: dict[str, Any]

class CeimBatchBody(ApprovalBody, total=False):
    standard: str
    representation: str | None
    entities: list[dict[str, Any]]
    relationships: list[dict[str, Any]]
    ceim_version: str | None
    resolution_case_ids: list[str] | None
    semantic_release: SemanticReleaseReference
    prefix: str | None
    source_system: str | None
    ontology_id: str | None
    publication_id: str | None

class ResolutionBody(ApprovalBody, total=False):
    selected_candidate_index: int | None
    strategy: Required[Text]
    rationale: Required[Text]

class RetryPolicyBody(RequestBody, total=False):
    max_attempts: Required[Annotated[int, Field(ge=1, le=5)]]
    backoff_seconds: Required[Annotated[int, Field(ge=1, le=3600)]]

class JobDefinitionBody(RequestBody, total=False):
    job_id: Required[Text]
    name: Required[Text]
    version: Required[Text]
    job_type: Required[Text]
    quality_profile: Required[Text]
    owner: str
    enabled: bool
    allowed_standards: list[str]
    retry_policy: RetryPolicyBody | None

class ScheduleBody(ApprovalBody, total=False):
    replay_run_id: Required[Text]
    interval_seconds: Required[Annotated[int, Field(ge=60, le=86400)]]
    retry_policy: RetryPolicyBody | None

class JobPublicationBody(ApprovalBody, total=False):
    prefix: str
    semantic_release: SemanticReleaseReference
    source_system: str
    ontology_id: str

class SysmlCommitBody(RequestBody, total=False):
    job_id: str
    job_version: str

class LegacyMergeBody(RequestBody, total=False):
    from_ontology_id: Required[Text]
    to_ontology_id: Required[Text]
    dry_run: bool

class LegacyCleanupBody(RequestBody, total=False):
    dry_run: bool
    delete_from_neo4j: bool
    batch_size: Annotated[int, Field(ge=1)]
    confirm: str

class ToolRunBody(AgentPlanBody, ApprovalBody, total=False):
    inputs: dict[str, Any]

class WorkflowRunBody(WorkflowPlanBody, ApprovalBody, total=False):
    inputs: dict[str, Any]
    step_inputs: list[dict[str, Any]] | None

class ToolSuggestionBody(RequestBody, total=False):
    task: Required[Text]
    context: dict[str, Any] | None
    attachment: dict[str, Any] | None

class CompensationBody(ReasonApprovalBody, total=False):
    sequence: Required[Annotated[int, Field(ge=1)]]

class DtManifestBody(RequestBody, total=False):
    manifest: dict[str, Any]
    steps: list[dict[str, Any]]
    sequence: list[dict[str, Any]]
    name: str
    entry_agent: str

class DtRunBody(ApprovalBody, total=False):
    execution_scope: Required[Text]
    query: str
    email: str
    workflow_id: str

class ModelNodeBody(RequestBody, total=False):
    properties: dict[str, Any]
    type: str
    label: str
    uid: str
    project: str
    package: str

class ModelLinkBody(RequestBody, total=False):
    properties: dict[str, Any]
    type: str
    source: str
    target: str

class ModelProposalBody(RequestBody, total=False):
    prompt: str
    message: str
    project: str
    context: dict[str, Any]
    document: dict[str, Any]
    metadata: dict[str, Any]

class ModelDecisionBody(ApprovalBody, total=False):
    rejected_by: str
    comment: str

class ModelSeedBody(RequestBody, total=False):
    project: str

class FederationPeerBody(ApprovalBody, total=False):
    peer_id: Required[Text]
    endpoint: Required[Text]
    ontology_allowlist: list[str]
    timeout_seconds: Annotated[int, Field(ge=1, le=30)]

class SpeedSourceBody(ApprovalBody, total=False):
    source_id: Required[Text]
    allowed_standards: Required[list[str]]
    name: str
    owner: str
    max_lateness_seconds: Annotated[int, Field(ge=0, le=86400)]
    retraction_policy: str

class SpeedEventBody(ApprovalBody, total=False):
    event_id: Required[Text]
    source_id: Required[Text]
    standard: Required[Text]
    occurred_at: Required[Text]
    event_type: str
    records: Required[dict[str, Any]]
    resource_id: str

class SpeedReconciliationBody(ApprovalBody, total=False):
    event_ids: Required[Annotated[list[Text], Field(min_length=1, max_length=500)]]

class BridgeMappingBody(RequestBody, total=False):
    candidate_id: Required[Text]
    import_id: Required[Text]
    import_row_key: Required[Text]
    ontology_class_element_id: Required[Text]
    target_ontology_type: Required[Literal["Class", "ObjectProperty", "DatatypeProperty", "AnnotationProperty"]]
    target_ontology_iri: str
    mapping: str
    ontology_term: str
    source_type: str
    mapping_type: str
    # Preserve the signed JSON value exactly; converting 1 to 1.0 changes the digest.
    confidence: Any

class BridgePublicationBody(ApprovalBody, total=False):
    publication_id: Required[Text]
    request_digest: Required[Text]
    preview_id: Required[Text]
    ontology_id: Required[Text]
    rows: Required[Annotated[list[BridgeMappingBody], Field(min_length=1, max_length=2000)]]

class InferenceRules(RequestBody, total=False):
    __pydantic_config__ = ConfigDict(strict=True, extra="forbid")
    transitive_subclass: bool
    domain_range_typing: bool
    equivalence: bool
    disjointness: bool
    individual_type_closure: bool

class InferenceBody(RequestBody, total=False):
    rules: InferenceRules
    limit: Annotated[int, Field(ge=25, le=1000)]

class ReportBody(RequestBody, total=False):
    type: str
    report_type: str
    page: Annotated[int, Field(ge=1)]
    page_size: Annotated[int, Field(ge=1, le=500)]
    pageSize: Annotated[int, Field(ge=1, le=500)]
    include_documents: bool
    includeDocuments: bool
    ontology_id: str
    ontology_prefix: str

class JobInputBody(ApprovalBody, total=False):
    records: list[dict[str, Any]]
    artifact_id: str
    artifact_ids: list[str]
    standard: str
    entities: list[dict[str, Any]]
    relationships: list[dict[str, Any]]
    representation: str
    ceim_version: str
    schema_artifact_id: str
    xml_artifact_id: str
    schema_dependencies: dict[str, str]
    documents: list[dict[str, Any]]
    evidence_artifact_id: str
    proposal_artifact_id: str
    source_system: str
    checkpoint: Any
    next_checkpoint: Any

class DocumentWorkflowBody(JobInputBody, total=False):
    stages: Required[dict[str, dict[str, Any]]]

class ProfileMapping(RequestBody, total=False):
    entity: str
    identifier: str
    properties: dict[str, str]

class SourceProfileBody(RequestBody, total=False):
    profile_id: Text
    name: Text
    version: Annotated[int, Field(ge=0)]
    mapping: ProfileMapping
    format: str
    namespace: str

class SourceRecordBody(RequestBody, total=False):
    __pydantic_config__ = ConfigDict(strict=True, extra="allow", json_schema_extra={
        "x-depo-dynamic-body": True,
        "description": "Source field names and values are defined by the selected source profile mapping; this endpoint accepts a single JSON object."})
    id: Any

OslcQueryBody = TypedDict("OslcQueryBody", {
    "oslc.where": str, "oslc.select": str, "oslc.orderBy": str,
    "oslc.searchTerms": str, "oslc.paging": bool | str,
    "oslc.pageSize": int | str, "oslc.pageNum": int | str,
    "approved_by": str, "approval_token": str,
}, total=False)
OslcQueryBody.__pydantic_config__ = ConfigDict(strict=True, extra="allow")
