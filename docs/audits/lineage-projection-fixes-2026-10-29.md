# Lineage contracts, retention and RDF projection fixes

This follows [the lineage audit](lineage-catalog-projections-2026-10-29.md). It preserves existing retained data and publication approvals.

## Changes

- Product validation rejects malformed source/ontology references and caller-supplied routes. Publication/preview resolves declared ontology and completed-run identities through configured owner APIs, verifies packaged artifact membership, captures owner-record digests and reports `resolved` versus `artifact_only` evidence. This does not claim graph publication or semantic compatibility. Peer reads are bounded to four concurrent requests, 8 MiB each and a 30-second overall deadline; failed checks cancel outstanding reads.
- Catalog delivery preserves business descriptions and lineage verification. Existing immutable descriptions can be backfilled only when their exact text was already present in the unchanged retained manifest. Other content changes still require a new version.
- Retention checks PostgreSQL references and retained usage provenance before purge, and repeats the check under the artifact file lock before deletion. Managed product/catalog writes and pipeline manifest creation/completion share maintenance exclusion with purge. Unknown/historical usage provenance remains protected rather than inferred inactive. There is no automatic consumer unpin or force-purge override; explicit reset workflows retain their separate confirmation requirements.
- RDF row construction indexes type/label/comment/source information rather than repeatedly querying RDFLib per resource. It retains language/datatype values, deterministic row/edge ordering and classification precedence. Blank-node descriptions/source annotations are now read using the actual RDF node identity.
- Graph loading rejects malformed projection payloads and mismatched returned ontology scopes; abandoned requests cannot install stale graph state. Exact graph identities are retained for node highlighting and Recommendations handoff. Projection calls have an explicit bounded timeout and use the configured graph service route.
- Projection test fixtures use the actual row builder, and replacement tests supply the real hashing dependency. The three previously disclosed harness failures now pass.
- Governed imports verify the selected job identity, version, approval/enabled status and allowed source standard before queueing. This prevents an accepted SysML upload becoming an opaque failed worker run when the selected baseline job permits only AP242/PLMXML/QIF/ReqIF. Approved baseline definitions are not silently rewritten. Product publication checks approval before expensive artifact validation/hashing.

## Performance evidence

The retained AP242 artifact originally imported from SPLM MBD3D_BO contains 315,976 triples and produces 70,052 resources / 197,372 relationships. A local before/after comparison returned identical complete row output. Previous row construction took 9.525 seconds; indexed construction took 6.185 seconds, a 1.54× speedup. Parsing separately took 17.835 seconds. This is one local measurement of row construction, not an end-to-end database/network throughput guarantee or a memory benchmark. Existing bounded worker, staging and activation mechanisms remain in use.

## Verification and operational limits

The initial broad backend run passed 102 cases; final focused catalog/retention checks passed 49 cases. Graph interaction/routing, product draft and catalog component tests passed 28 cases. Overlapping runs must not be added as a count of unique tests. Machine-readable results and subsequent live/SPLM acceptance are retained with this audit's evidence.

No automatic graph publication or ontology approval is introduced by product packaging. Source inspection/import tests may retain artifacts and workflow records; a completed validation run is not a graph publication receipt. Customer-server routing, live LLM responses, full cross-store restoration and visual browser acceptance require separate qualification.

## SPLM data qualification

Live local testing used files from `D:\GenAI_Projects\SPLM_Folder`, with LLM disabled and no graph/product publication requested:

| Source | Outcome |
| --- | --- |
| PLMXML induction-motor requirement specification | Completed/conforms; 14 normalized entities; source SHA-256 retained in run input |
| STEP SKF bearing part (`000680…Prt3.stp`) | Completed/conforms; 150 entities / 131 relationships |
| SugarPlantMBSE XMI | Initial baseline job rejected SysML by configuration; separate scoped SysML job completed/conforms with 791 entities / 497 relationships and was disabled afterward |
| AP242 `MBD3D_BO/DomainModel.xsd` | Inspection returned HTTP 200; 889,321-byte source converted to 21,205,084-byte retained RDF plus analytics/SHACL artifacts |
| Scoped existing AP242 graph slice | 80 nodes / 127 relationships; all start/end IDs belong to the slice; correct ontology scope; node neighborhood HTTP 200 |
| Product preview using actual PLMXML run/source artifact | Valid with resolved owner-record digest; graph-publication verification explicitly false; malformed lineage rejected |

The failed initial XMI run remains in audit history with its configuration failure, rather than being erased. The test job did not alter the original approved baseline. The graph endpoint assertion uses its documented `start`/`end` identity fields. No claim is made that XSD conversion alone publishes an ontology or materializes an analytics warehouse.

After the live-discovered routing check, 20 focused routing/auth/lineage cases passed. Evidence files are under [the qualification directory](lineage-projection-fixes-2026-10-29/); overlapping test totals are not additive.

## Final installed acceptance

The final managed restart completed using `/assets/index-CNNcqwiy.js`; frontend HTTP 200 and all ten API readiness checks passed. LLM remained disabled. Installed changed runtime files matched the tested workspace. A live repeat of the incompatible SysML/default-job request returned HTTP 422 with the standard mismatch explained, and the run count did not increase: no additional failed job was queued.

The graph remained at 306,402 resources / 928,541 relationships. The dedicated SysML test definition was disabled after its conformant run. No source test requested graph or product publication. A read-only reference check also verified that a real retained ontology artifact is protected from purge. See [final acceptance](lineage-projection-fixes-2026-10-29/final-live.json) and [SPLM records](lineage-projection-fixes-2026-10-29/splm-live.json).

Local deployment backups: `logs/prompt-audit-update/20261029-084253-58c6a9e372ae41f6835098fffec0e67c` and `logs/prompt-audit-update/20261029-085620-f87185ede8c2490bacada4966dd5e4d5` under the installed PMem root. Environment files and database data were preserved.

## Browser follow-up and inventory session fix

Browser checks exercised Import history, Data Flow run filtering and retained SysML run evidence, Catalog source/product tabs, and Graph Explorer overview loading. Catalog showed 14 retained imports and two registered ontologies; zero published products was an explicit empty state. The selected SysML run correctly reported completed validation and no graph publication. Graph overview returned a bounded 448-node / 516-link slice, rather than database totals.

Confirmed defect: IngestedDataInventory listened only for credential changes, so session replacement/expiry or successful access revalidation could leave stale inventory or a retained error. It now reloads on these events, aborts prior requests, ignores late responses, and removes listeners on unmount. Three adversarial session-event tests plus adjacent inventory, product and navigation tests passed: 22 cases. The installed frontend rebuilt successfully as /assets/index-CMroMJ_r.js and its launcher verified browser authentication and ontology reads. Only the frontend restarted; code backup is under logs/inventory-session-fix.

Open observations, not closed findings: direct automated hash navigation twice changed Catalog to Registry after initial rendering; menu navigation and a subsequent reload remained on Catalog. No route alias defect was established or speculative routing patch applied. Initial health/verification also showed transient degraded states despite later successful reads. These timing observations need further tracing; this browser pass does not qualify every graph mode, publication action, or LLM workflow. Legacy retained Import messages still contain database implementation terminology. No records were deleted or published during this follow-up.
