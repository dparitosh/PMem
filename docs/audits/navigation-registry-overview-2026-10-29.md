# Navigation, session status and workspace UI audit — 2026-10-29

## Confirmed fixes

- AppShell verification result handling now checks request ownership. A verification that finishes after a newer access rejection or session change cannot overwrite that state or navigate to Admin.
- Application health checks use a 15-second request budget and recheck immediately on successful access verification. Cancelled samples cannot set Online/Degraded/Offline. Genuine failures remain visible.
- Metadata Registry now resets reads and mutations on session replacement/expiry and refreshes read data on access verification while preserving the selected dictionary source. Existing AbortControllers reject stale responses.
- Dictionary table uses fixed column widths, term-first presentation, expandable IRI/full definition, sticky headings, and 25-row pagination. Search resets pagination; draft preparation still preserves the exact source IRI and does not write until Register.
- Grouped overview uses responsive selectable source tiles with entity/link counts and group filtering. It retains exact provenance membership, cross-group connection evidence, entity inspection and registered ontology links. Technical identities are expandable. Removed the scale-to-fit SVG that made many groups illegible. The separate Entity graph visualization remains available.
- Scoped graph styles override legacy broad button effects and Bootstrap legend layout without changing other pages.

## Verification

35 regression cases passed across MetadataRegistryPage, OntologyGroupOverview, App and AppShell. Tests include pagination, filtering, changed slices, source IRI preservation, no premature registration, late verification, reconnect health refresh, and separate Catalog/Registry history routes. Production build passed with 3,441 modules; existing chunk-size and test-library deprecation warnings remain. Installed frontend asset: `/assets/index-ahpMmkJx.js`. Code backups are under installed `logs/ui-session-fix/`.

Live browser: Registry loaded 2,230 PLMXML dictionary terms with readable aligned columns. Catalog direct navigation remained on Catalog after loading; service status and read access showed Online/verified. No page-wide horizontal DOM overflow was detected at 1,265px viewport. The earlier Catalog-to-Registry redirect was not reproduced on this fresh browser tab and is not claimed as a root-caused routing fix. Routing regression coverage was added; no speculative alias change was made.

Frontend only was restarted. No credentials, database records, approval rules or LLM configuration changed. No publication or deletion was performed.
