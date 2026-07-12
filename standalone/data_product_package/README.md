# Standalone Data Product Package Builder

This package is an isolated, file-system-only builder for governed engineering data products.
It does not import the DEPO backend, frontend, Neo4j driver, or FastAPI application.

## What it produces

Each build creates a versioned directory and ZIP containing:

- `manifest.json` with product metadata, source lineage, artifacts, checksums, and validation results
- copied source artifacts such as OWL, RDF, TTL, JSON-LD, mappings, reports, and graph extracts
- `catalog.json` when the Excel product catalog is supplied
- `README.md` describing the package contents

## Usage

From this directory:

```powershell
python -m data_product_package --catalog-xlsx D:\dataproduct1.xlsx --output .\output
```

Build from a product specification:

```powershell
python -m data_product_package --spec .\examples\ap242_product.json --output .\output
```

The specification is intentionally file based so it can later be populated by the existing API without coupling this package to it.

For an application integration, use `data_product_package.integration.build_from_app_outputs`.
Pass explicit exported artifact paths, ontology registry records, import-task
lineage, and product metadata. The adapter performs no API or Neo4j calls.

## Specification shape

```json
{
  "product_id": "dp-ap242-001",
  "name": "AP242 Engineering Traceability",
  "version": "1.0.0",
  "domain": "MBD3D AP242",
  "description": "Ontology-backed part, PMI, requirement, and traceability package.",
  "owner": "Engineering Data",
  "ontologies": [{"id": "ap242", "name": "AP242", "prefix": "ap242"}],
  "sources": [{"id": "import-001", "type": "ImportTask", "name": "sample.stpx"}],
  "artifacts": [
    {"path": "D:/exports/ap242.ttl", "kind": "ontology", "format": "ttl"},
    {"path": "D:/exports/graph.jsonld", "kind": "graph", "format": "jsonld"}
  ]
}
```

Paths must exist and must be files. The builder copies them into the package and never deletes or modifies the source files.

## Integration boundary

The live application can later call this package from a dedicated adapter or job worker. The planned adapter contract is:

```text
POST /api/v1/data-products/preview
POST /api/v1/data-products/{id}/build
GET  /api/v1/data-products/{id}/download
```

Those routes are deliberately not added to the current application by this isolated package.
