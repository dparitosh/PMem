# Extra-large ontology audit — 2026-10-21

Scope: source inspection of engineering upload/conversion, catalog registration/read, taxonomy/export, merge preparation/reasoning and graph publication; synthetic RDF inventory/projection checks; isolated boundary regressions. This is not certification for arbitrarily large ontologies or a live large-data publication acceptance test.

## Findings corrected

1. **Generated results can outgrow downstream limits.** The engineering worker permits a 256 MiB result by default, while registration/publication share a default 25 MiB artifact limit. Engineering ingestion now checks the generated Turtle byte size before requesting policy/quality/registration and identifies the setting to change across the owning services. The upload/registration limit remains explicit; it was not silently raised.
2. **Catalog size errors were hidden as RDF syntax errors.** Catalog parsing now rejects oversized content before trying RDF formats, retaining the actionable size-limit cause.
3. **Retained catalog reads allocated the complete file without a limit.** Reads now reject an oversized file from its stat before opening it and use a bounded read plus post-read verification, including protection against growth after the initial stat. Existing catalog-directory containment checks remain in place.
4. **Background merges serialized inputs twice and copied complete output bytes.** Preparation no longer builds an unused serialized byte buffer before dispatching a background job. Background worker transport writes pickle directly to its source file, checks result size from the output file and decodes directly from it.
5. **Conversion output spooling enforced size only after process exit.** The trusted conversion worker now writes through a bounded writer and exits with a dedicated status before output exceeds its configured limit. The parent translates that status into the recovery-setting error and closes temporary files. This bounds serialized result output, not converter graph memory or diagnostic output.

The broader catalog regression run exposed five tests that used an in-memory registry but still attempted a maintenance lock against a deliberately fake PostgreSQL URL. Those fixtures now isolate the database lock context. Production maintenance locking is unchanged and remains required.

## Limits that still apply

| Boundary | Current behavior | Consequence for large data |
| --- | --- | --- |
| Source/artifact size | `ONTOLOGY_MAX_UPLOAD_BYTES`, default 26214400 bytes, is shared by upload, catalog registration, export, graph publication and merge source budgets. | Configure consistently on all owning services. Increasing the conversion result limit alone is insufficient. |
| Companion XSD closure | At most `min(25 MiB, ONTOLOGY_MAX_UPLOAD_BYTES)` across the root and dependencies. | Increasing the general artifact setting does not permit a schema bundle over 25 MiB. Larger source bundles require a separately designed/tested change. |
| Engineering worker result | `ENGINEERING_CONVERSION_MAX_RESULT_BYTES`, default 256 MiB, maximum 1 GiB. | Includes conversion metadata/analytics as well as Turtle; it is not the raw upload limit or an RSS ceiling. |
| Combined merge sources | Aggregate input budget is `ONTOLOGY_MAX_UPLOAD_BYTES`. | Two individually permitted artifacts can exceed the combined budget. Partition the merge or provision a sufficient aggregate budget. |
| Merge proposals | Candidate/comparison/output limits are enforced by `merge_matching.py`. | Proposal review may be incomplete; a bounded search is not exhaustive semantic alignment. |
| Graph publication | Staged batches, manifest verification, resumable offsets and activation checks exist. | Full parsed RDF and projection structures are still constructed before batching; batching does not make parsing constant-memory. |

## Remaining scalability risks

These remain open; the corrections above do not establish extra-large production capacity.

- **High — in-process registration/quality memory and CPU.** Catalog registration parses the complete RDF graph in a thread. Engineering quality builds a complete subject inventory and sends it as JSON. These do not have a terminable child/resource quota covering every expensive step. Cancelling a request does not reliably terminate a running parser thread. Repeated full graph parsing and syntactic-equivalence checks add cost.
- **High — publication and synchronous semantic worker buffers.** `rdf_preparation.py`, synchronous `merge_preparation.py` and `merge_semantics.py` still use captured subprocess results/serialized payloads. RDF preparation constructs full graph/projection objects, and the parent reconstructs them. This can require several times the serialized RDF size. Remaining worker paths need file/artifact transport and measured resource budgets.
- **High — inference and blank-node canonicalization expansion.** OWL-RL closure and structurally symmetric blank nodes can expand work far beyond ordinary class hierarchies. Existing deadlines and conservative approval holds must remain; do not skip semantic validation to achieve throughput. Large cyclic, restriction-heavy and blank-node-heavy acceptance fixtures are still needed.
- **Medium — browser/cached taxonomy payloads.** Taxonomy caches retain up to 32 complete payloads and return deep copies. Full vocabulary/dictionary requests and client-side tables can become expensive even when ontology catalog metadata is paginated.
- **Medium — graph-native fallback slices.** The fallback taxonomy query limits nodes to 5,000 and relationships to 10,000. Treat that response as a graph slice rather than complete ontology coverage; paginated traversal with explicit completeness metadata is still needed.
- **Operational — no proven maximum supported size.** Byte limits are administrative bounds, not capacity guarantees. Concurrent conversions, worker graph memory, diagnostic disk output, Postgres metadata growth and Neo4j activation/rollback need representative load and recovery tests on the target machine.

## Verification evidence

The new boundary regressions cover UTF-8 byte size rather than character count, no downstream registration request after an oversized generated ontology, catalog rejection before parsing/opening oversized retained files, merge output limits before decoding, direct file decoding, bounded conversion writes and dedicated limit-exit reporting. Existing governance, deadline, catalog, projection and publication batching regressions were exercised too.

Synthetic hierarchy results from this workstation:

| Declared classes | RDF triples | Turtle bytes | Inventory parse seconds | Projection seconds | Verified subclass edges |
| --- | --- | --- | --- | --- | --- |
| 1,000 | 2,999 | 100,729 | 0.153 | 0.094 | 999 |
| 10,000 | 29,999 | 1,036,728 | 1.519 | 0.922 | 9,999 |
| 25,000 | 74,999 | 2,641,727 | 3.916 | 2.456 | 24,999 |

Every generated class IRI was compared with the prepared projection, and declared class/subclass counts were exact. These timings cover parsing/inventory and local row preparation; they exclude network transfer, semantic closure and Neo4j writes. They are observations, not performance targets. Separate transport regression preserves a generated result over the former 32 MiB cutoff. No representative million-triple, multi-gigabyte, concurrent-load or live large-ontology Neo4j acceptance run was performed. The customer source that originally failed has not been rerun against this audit revision.

## Required customer acceptance before an extra-large support claim

Use an isolated test database and representative source, dependent schemas and reasoning shapes. Measure peak worker/parent RSS, temporary disk consumption, request latency, database growth and exact inventory counts at increasing sizes and concurrency. Verify service health during work, cancellation/restart, resumed graph batches, failed activation, unchanged active publication after failure, deterministic identities, complete browse/export and retained validation evidence. Establish documented supported size/concurrency limits only from those results.
