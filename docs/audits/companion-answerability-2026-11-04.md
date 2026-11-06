# Companion answerability correction

## Confirmed defects

- A typed business lookup with zero rows previously returned `answerable: true` at the final Companion boundary.
- Part–PMI source references could permit model interpretation even though ownership remained unverified.
- Retrieval of matching records did not establish an executed count, aggregate or approved KPI calculation.

## Correction

The Companion now reports insufficient evidence for empty typed lookups and unverified ownership for source-reference-only PMI results. It retains evidence and deterministic explanations but suppresses model interpretation for those results.

Explicit quantitative questions return `unsupported_calculation` before retrieval or generation, with an instruction to choose an approved analysis and define formula, units and scope. This conservative guard does not implement arbitrary SQL generation. Descriptive questions remain eligible for existing retrieval.

Semantica continues to provide existing context and ontology facilities. No additional platform, package or memory store was introduced.

## Validation and limits

Regression tests cover empty results, ownership candidates, model-call suppression, quantitative requests and descriptive vocabulary questions. The focused answerability, prompt and boundary suite passed 20 tests and 5 subtests. The existing domain-evidence and accuracy suite passed another 17 tests, for 37 tests and 5 subtests overall.

This is a deterministic coverage guard, not a semantic proof that every retrieved sentence answers a question. Comprehensive natural-language intent classification, approved measure execution and evaluated query generation remain separate work. No live LLM acceptance test was performed.

## Deployment

Deploy `backend/agentic_service/answerability.py` together with the updated Companion module using the existing release process and restart the agentic service. No PostgreSQL migration, new setting or credential is required. These changes are in the source checkout; they have not been applied to the running installation by this change.
