# Shared decision-policy integration audit — 2026-10-22

The active Recommendations Graph API, retained monolith recommendation endpoints and legacy recommendation tools now invoke the existing native Semantica decision evaluator through one shared adapter. Instance linking and ontology merging use the same central policy registry. Existing Governor and Steward roles are retained.

Fixed: empty policy sets no longer imply compliance; policies declare operation scope; unsupported native rule names fail; PostgreSQL/evidence failures hold writes; both manual and automatic write paths reassess current rules. Verified graph receipts reconcile committed writes before new policy assessment, including response-loss retries. Shared assessments bind policy and decision digests and retain all checks separately in PostgreSQL. Responses contain at most 200 checks and all blocked decision indices; omitted rows cannot become eligible. Configuration lookup reads only policy-prefixed keys, excluding unrelated version history.

The active similarity API previously derived scores from alphabetical row position. Scores now use explicit token/type evidence, with stable ranking over a bounded set. No claim of calibrated confidence or engineering equivalence is made. General recommendations and ontology unions do not manufacture a confidence score for native minimum-confidence rules.

User experience: Recommendations, instance bridge review and merge Steward review show whether shared policies are absent, passed, blocked or unavailable. Holds include readable native findings and mapping subjects. Policy checks supplement SHACL, OWL-RL, identity and lifecycle gates; they do not approve publication.

Validation: native Semantica was exercised with an in-memory registry. Tests cover policy scope, unknown rules, missing confidence, policy/evidence storage failure, changed policies, manual/automatic bypass attempts, idempotent receipt reconciliation, bounded large-batch findings and evidence-based recommendation ranking. Existing workflow, API request and UI regression suites were run. Production frontend build passed. See the execution results recorded in the task for exact suite counts.

Limitations: these are source-level and isolated integration checks. The updated runtime is not deployed or end-user verified in the live desktop installation. Windows process inspection in the agent session cannot verify tracked live executables; use the existing checked updater from the normal Windows administrator session. The updater preserves PostgreSQL, Neo4j, credentials and domain data. No ontology was approved, published or deleted during this change. Registry audit records are operational records, not a certified immutable ledger.


The subsequent microservice review moved consumer policy checks to the existing Ontology HTTP API, preserving lean isolated runtimes. The Ontology merge service evaluates locally. It also corrected ingestion's handling of absent policies and removed its fabricated confidence/approval values. See `microservices-review-2026-10-22.md` for the current cross-service contract and deployment verification.
