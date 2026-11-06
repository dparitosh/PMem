# Business-context and database audit — 26 October 2026

## Findings and corrections

- The Graph Analyst could read ontology neighborhoods but lacked a business-instance evidence operation. The existing agent now has bounded search, business-context and indexed-excerpt tools. Selected `node_id` is part of the immutable goal scope. No additional agent was introduced.
- Knowledge Companion previously used lexical graph hits without connected nonmatching neighbors. On the Graph page, an unambiguous identity now resolves to its connected business neighborhood. Ambiguous results require selection; unrelated hits are not silently joined.
- Business-context responses include relationship identities and inclusion paths. Source references, recorded semantic mappings and other recorded relationships are distinguished. None establishes causal impact, approved equivalence or semantic entailment.
- Recommendation reads now preserve canonical `rdf_types` and RDF relationship predicates. Storage labels such as `OntologyResource` no longer contribute a type-similarity bonus. Similar-part candidates respect selected ontology scope and reuse graph search.
- Canonical search previously wrapped properties in lowercase functions, preventing the desired text-index path. Derived lowercase fields and TEXT indexes support direct contains predicates. Publication maintains those fields; bootstrap backfills existing resources in bounded transactions.
- PostgreSQL pagination now matches the existing `(namespace, updated_at DESC, key ASC)` index. Status reads use an indexable fixed JSON expression. Migration 13 adds status/recent and job identity indexes, with schema-definition verification and immutable migration history.

## Measured database evidence

The live Neo4j PROFILE for canonical `motor` search used two `NodeIndexContainsScan` operators. It returned six candidates; cold server timings were 699 ms available and 200 ms consumed, including planning/cache effects. This is a plan verification, not a workload benchmark or speedup guarantee. Backfill verification found zero published resources missing derived search fields. The retained-excerpt FULLTEXT index was ONLINE.

PostgreSQL EXPLAIN ANALYZE measured 0.342 ms for the small recent-job page and 0.034 ms for a queued-goal status lookup. The latter naturally used `idx_depo_registry_status_recent`; the former chose a sequential scan plus sort on the small registry. Transaction-local index-eligibility plans are diagnostic only; no production planner setting was changed. Do not infer large-dataset latency from this small sample.

A direct live AP242 read returned 40 connected business objects and 40 relationships with truncation explicitly reported. The retained-document query returned `no_evidence`. Original graph publications were not replaced by these additive schema changes.

Raw local evidence is retained outside source control in `outputs/business-context-db-audit.json`, `outputs/business-context-optimized-plans.json` and `outputs/business-context-live-example.json` in the audit workspace. These files contain deployment-specific identities.

## Remaining limits

Legacy heterogeneous imports retain scan-based search fallbacks. Canonical candidate discovery is capped per term and scope; it is not exhaustive search. Existing identity and scope indexes were already active and remain in use. No unnecessary replacement of those indexes was made.

This update adds lexical excerpt retrieval, not embedding generation or vector GraphRAG. Source revision freshness remains unverified. Document ingestion coverage, complete instance-to-ontology semantic alignment, approved AP242–QIF mappings and coordinated PostgreSQL/Neo4j/artifact restore acceptance remain separate work. A bounded graph connection must not be presented as engineering impact or calibrated confidence.

## Operational sequence

Apply the complete release, run supported PostgreSQL migrations, bootstrap Neo4j indexes/backfill, validate schema, then restart backend services together. Preserve environment files and publication receipts. See `INSTALLATION.md` for exact PowerShell filenames and commands. Schema setup is idempotent; no database recreation, credential rotation, mapping approval or publication is performed by this change.

## References

- [Neo4j index use and query plans](https://neo4j.com/docs/cypher-manual/current/indexes/performance-indexes/using-indexes/)
- [Neo4j search indexes](https://neo4j.com/docs/cypher-manual/current/indexes/search-indexes/)
- [PostgreSQL CREATE INDEX](https://www.postgresql.org/docs/16/sql-createindex.html)


## Deployment acceptance

Deployed to `D:\GenAI_Projects\Apps\PMem` with matching source checksums and backups at `logs/business-context-audit-backup/20261026-002548`. All ten backend readiness endpoints (8010–8019) returned HTTP 200. Live business-context returned HTTP 200 with 40 nodes/40 edges; a mismatched ontology scope returned 404 and omitted credentials returned 403. Indexed document retrieval returned HTTP 200 / `no_evidence`. The existing Graph Analyst catalog advertises the three new read tools. All 23 retained AP242 publication receipts still report `published`.

Validation: the combined final regression suite passed **184 tests** across business context, graph search, Companion evidence/boundaries, read-goal control, agent catalog, migrations, PostgreSQL/Neo4j schema contracts and publication recovery. The outdated publication-status fixture now supplies its module/import context and current artifact-digest contract. No frontend code was changed, so no new frontend build was required. Live LLM generation was not validated; these results establish retrieval and controller contracts, not model answer quality.

Warm live context reads returned HTTP 200 in 1.938 s and 1.718 s for the same 40-node limit. These are local spot checks, not concurrency or customer-scale benchmarks.
