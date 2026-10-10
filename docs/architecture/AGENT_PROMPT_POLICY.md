# Agent prompt policy

Proposal policy `proposal-v2` selects one allowlisted tool. Native mode returns exactly one function-call proposal; structured mode returns a validated `tool_id` and `inputs` object. Neither mode grants approval or executes the proposed tool. Server credentials, lifecycle checks and explicit execution requests remain authoritative.

Catalog prompts must be nonempty text within 16,384 UTF-8 bytes. Each generated prompt snapshot includes its system-prompt SHA-256 hash as well as the configured version label. Governor and steward role instructions describe proposal and evaluation responsibilities rather than model-issued authorization or reports in proposal mode. Legacy chat uses an explicit untrusted-evidence and approval boundary.

Before inference and recommendation persistence, credential fields, known configured secret values, bearer credentials and recognizable password/token assignments are redacted. Companion input and graph evidence follow the same policy. Read access also redacts older recommendation records; this does not erase their original stored bytes. Arbitrary unlabeled secrets cannot be reliably identified, so do not enter credentials in task text or evidence. Historical persisted records require separate administrator review.

Companion summaries must cite supplied identifiers using `[evidence:IDENTIFIER]`. Missing or invented citations reject the model summary and preserve deterministic graph evidence. This validates citation membership, not whether every statement is entailed by its citation. Model streams are buffered until completion and citation checks pass; deterministic retrieval status may still stream immediately. The chat status endpoint reports buffered generation delivery.
