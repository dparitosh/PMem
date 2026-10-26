# Engineering recommendation review

## Business workflow

1. Import and map the customer's business instances to their ontology. Parts, assemblies, changes, requirements and processes need declared business types or retained mappings. Schema definitions alone do not supply instance evidence.
2. In Graph Explorer select the exact object and revision, then open Similar Parts or Change Impact. The graph inspector preserves the object identity and scope. In Recommendations, a manually entered name must resolve unambiguously; select the exact identity in the graph when names collide.
3. For Similar Parts, review the comparison rows. For example, `25.4 mm` and `1 in` compare equally; `10 mm` and `11 mm` conflict. A numeric value without a unit remains unassessed. A matching name cannot override a material, dimensional or configuration conflict.
4. For Change Impact, follow the retained path. An example is `Change → impacted-item relationship → Bearing → Drive assembly → Vibration requirement`. Inspect configuration differences and effectivity before deciding whether those records belong to the active product baseline.
5. Review decision-policy findings and missing evidence. Agent mode plans the investigation and cites the same retained graph result. Direct graph mode remains available when the language model is unavailable.

## Evidence and scoring

Similarity uses a declared business category (15%), name token/trigram similarity (20%) and declared engineering-property matches (65%). Missing engineering properties earn no engineering points. The current comparison fields are material, diameter, length, width, height, mass, tolerance, specification, revision, configuration and effectivity. These fixed weights rank evidence; they are not calibrated confidence or an interchangeability certification.

Dimensions support `mm`, `cm`, `m`, `in`, `inch`, `inches`, `um` and `µm`; mass supports `g`, `kg`, `lb` and `lbs`. Numeric comparisons use explicit compatible units and numerical conversion precision. They do not infer acceptable design tolerances from nearby numbers. Multiple property values, unsupported units, interval expressions and undeclared material equivalence require review.

Vocabulary local names include material/materialName/materialGrade, diameter/nominalDiameter/outerDiameter, specification/specificationId/standard, revision/revisionId and configuration/configurationId/variant. The engine reads direct properties and retained RDF literal properties. Custom class names should map to declared business roles; custom engineering predicates should use the supported vocabulary or be added with domain-reviewed comparison tests.

Traversal is limited to four physical hops, 200 records, 600 eligible relationships per frontier and a 20-second graph-read budget. Candidate retrieval is limited to 200 typed records and returns up to 50 requested results. The dependency diagram shows up to 60 records; the evidence table retains the remaining results. A reached limit is visible. Results do not claim whole-graph completeness.

## Configuring an advisory evidence policy

Policies are governed configuration. Review them with the customer's engineering owner and create them through the existing authenticated ontology policy API (`POST /api/v1/ontologies/policies`). Use the configured service credentials; do not put keys into source files or example payloads.

Example policy body:

```json
{
  "policy_id": "engineering-advisory-review",
  "name": "Engineering evidence review",
  "operations": ["recommendations"],
  "rules": {
    "min_confidence": 0,
    "required_outcomes": ["flagged"],
    "required_metadata": ["decision_maker", "result_digest", "candidate_id"],
    "max_conflicts": 0,
    "min_evidence_coverage": 0.6,
    "allowed_evidence_statuses": ["requires_engineering_review"]
  }
}
```

`min_confidence: 0` deliberately avoids imposing a calibrated-probability requirement on this advisory operation. It does not grant approval. The engineering rules still hold conflicting, incomplete or otherwise unsuitable evidence. This example allows only the similarity review state; change-impact candidates will be held until the customer defines an appropriate policy for their evidence states. Operation-wide policies apply together, so review their combined effect.

Additional supported rules are `require_complete_coverage` and `require_effectivity_verified`. They hold current bounded/unverified impact advice when set to `true`. Do not disable them to claim complete or active impact when that evidence has not been established. Native Semantica policy checks and PMem engineering rule extensions are identified in the retained assessment.

## Updating an existing installation

From the repository root, run the documented `update-depo.ps1 -PreflightOnly` command, then the same updater without `-PreflightOnly`. Deploy the whole release, including `backend/graph_service/recommendation_engine.py`, `engineering_comparison.py` and `backend/Services/recommendation_compat.py`; release preflight checks these files. Rebuild the frontend and restart the application through the updater. Existing data, credentials and histories remain retained. No engineering policy is installed automatically.

After refresh and access revalidation, check the expected results using customer-owned fixtures: duplicate names across revisions, equivalent units, incompatible materials, differently named parts, multi-hop BOM effects, change carriers, missing mappings, unavailable policy/model services and truncated graph neighborhoods. Record expected inclusions and exclusions with the customer before claiming production acceptance.
