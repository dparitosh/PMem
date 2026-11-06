# PLMXML Metadata Filtering Notes

This change keeps the existing PLMXML parsing flow, dataclasses, and reference-resolution model intact while preventing metadata-only XML elements from becoming standalone graph nodes.

## Existing Functions Changed

### `backend/Services/plmxml_parser.py`

#### `parse_plmxml_file(file_path, metadata_exclusion_tags=None)`
Why it changed:
- Added an optional `metadata_exclusion_tags` parameter so metadata suppression can be configured without replacing the parser.
- Preserved the existing iterparse-based flow, ID assignment, duplicate detection, alias resolution, and relationship candidate collection.
- Fixed the existing child-element handling issue where nested `UserValue`, `Description`, `ApplicationRef`, and nested `UserData` content could be cleared before the parent element consumed it.

Behavior impact:
- `UserData`, `Form`, and configured metadata-only tags are still parsed into the existing document structures, but they are now explicitly classified for downstream filtering.
- `parse_stats["metadata_exclusion_tags"]` now records the active exclusion list used during parsing.

#### `_resolve_metadata_exclusion_tags(metadata_exclusion_tags=None)`
Why it changed:
- Centralizes the configurable metadata exclusion policy.
- Merges built-in defaults with optional caller-provided tags and the `PLMXML_METADATA_EXCLUSION_TAGS` environment variable.

Behavior impact:
- Makes metadata tag suppression configurable without changing the domain parser logic.

#### `_is_metadata_only_tag(tag, metadata_exclusion_tags)`
Why it changed:
- Added a small helper so metadata-only classification is explicit and reusable.

Behavior impact:
- Keeps `Form` and generic metadata tag classification deterministic and easy to audit.

### `backend/Services/unified_data_import.py`

#### `UnifiedDataImportService.start_import(..., parse_options=None)`
Why it changed:
- Added a task-level parse-options channel so the metadata exclusion policy can be passed through the existing upload/import pipeline instead of remaining parser-internal only.

Behavior impact:
- The import task now persists caller-supplied PLMXML metadata exclusion tags and makes them available to the parse phase and status metadata.

#### `FileParser._parse_plmxml(file_content)`
Why it changed:
- This is the existing graph-row creation point for PLMXML imports, so metadata-only filtering had to happen here before rows become graph nodes.
- Reused the dedicated parser output instead of replacing it.

Behavior impact:
- `UserData` rows are no longer emitted as standalone graph rows.
- Metadata-only `Form` and structural/generic metadata tags are skipped as graph rows.
- Referenced metadata is folded into valid domain rows as properties instead of becoming nodes.
- Existing domain rows for `Product`, `ProductRevision`, `Part`, `Occurrence` / `ProductInstance`, BOM structure, `InstanceGraph`-style references, and normal reference resolution remain in the same import flow.
- Relationship emission now suppresses edges that would otherwise point to filtered metadata-only nodes.

### `backend/main.py`

#### `upload_file(...)`
Why it changed:
- Added `metadata_exclusion_tags` as an optional upload form field so callers can configure PLMXML metadata-node suppression without code changes.

Behavior impact:
- The HTTP upload contract now forwards the exclusion list into the unified import pipeline and echoes the resolved list in the upload response.

## What Was Intentionally Preserved

- Existing PLMXML dataclasses such as `PlmxmlPart`, `PlmxmlProductInstance`, `PlmxmlProductView`, `PlmxmlRevision`, `PlmxmlRequirement`, and `PlmxmlRelationship`
- Existing ID normalization via `_normalize_ref`
- Existing unresolved-reference reporting
- Existing duplicate-ID detection
- Existing reference candidate collection and relationship generation for valid domain entities
- Existing working behavior for product structure, BOM-style child references, and reference resolution across valid PLM entities

## Default Metadata Exclusion Tags

Built-in defaults now include:

- `AccessIntent`
- `AssociatedAttachment`
- `ApplicationRef`
- `Description`
- `Form`
- `PlainText`
- `UserData`
- `UserValue`

Additional tags can be supplied through:

- `parse_plmxml_file(..., metadata_exclusion_tags=[...])`
- `PLMXML_METADATA_EXCLUSION_TAGS=TagA,TagB,...`

## Tests Added

The existing PLMXML parser test module now verifies:

- configured metadata exclusion tags are surfaced by the parser
- metadata XML elements do not become graph rows
- valid PLM domain entities still become graph rows
- useful metadata from `UserData` and `Form` is retained as properties on valid domain rows
